# Generate harnesses

This page shows how to turn your devices and links into harnesses (connectors, pins and wires), check the result, and read why the tool made each choice.

## Contents

- [Before you start](#before-you-start)
- [1. Generate](#1-generate)
- [2. Check the result on its own](#2-check-the-result-on-its-own)
- [3. Read why a wire is the way it is](#3-read-why-a-wire-is-the-way-it-is)
- [How links become harnesses](#how-links-become-harnesses)
- [How auto-linking and the checks work](#how-auto-linking-and-the-checks-work)
- [Keep a choice of your own](#keep-a-choice-of-your-own)
- [Common mistakes](#common-mistakes)

## Before you start

- You have a project with devices and links. For a quick start make one: `harness-design-studio new wheel-link --template first-steps` (see [draw the design](draw-the-design.md)).
- A **harness** is a bundle of wires with connectors that carries the links between two devices. You do not draw it: the tool generates it from your design, and it can generate it again at any time. (A harness with no interface behind it you can make by hand: [build a harness by hand](build-a-harness-by-hand.md).)
- Wire gauges (thicknesses) stay *pending* until the engineering values exist. That is normal. See [fill in the engineering values](fill-in-engineering-values.md).

## 1. Generate

**In the app** (GUI, not run)

1. Press **Generate** in the top bar (**Design > Generate harnesses**, Ctrl+G). On the Next step page of the Systems engineer role the button is **Generate the harnesses**; it does the same.
2. A window shows a **preview** of what would be added, changed and removed. Nothing changes until you press **Apply**. (**Cancel** leaves the project as it was.)
3. The **Harness** tab (the **Drawings** area of the rail) opens on the result. To take it back, press **Undo** (Ctrl+Z). One Undo reverses the whole generation.

Generate always covers every harness; the app has no way to generate only one. The **Generate** step in the top bar says what it knows: *not generated yet*, *the harness plans match the design* or *the design changed after the last generation* (hover it). In the last case the status chip says *Plans out of date* and a banner offers **Generate**.

If there is nothing to generate the app says so ("There is nothing to generate yet. Add devices and connect them with interfaces first." or "Harnesses are already up to date. Nothing to change."). If generation finds problems (for example an interface that has no free pins), the preview opens with the errors listed ("Some harnesses could not be generated (N problem(s)). Fix the connectors or interfaces named in the list, then generate again."). It never says "up to date" while errors are waiting. If you edit the project while the plan is being made, the plan is refused ("The project changed while the plan was being made, so nothing was applied. Press Generate again.").

**On the command line**

```
harness-design-studio generate wheel-link
```

```
2 added, 0 changed, 0 unchanged, 0 removed, 0 frozen (released); 0 locked pin(s) kept
2 interfaces and 6 wires checked: 0 error(s)
```

Two harnesses were made, one for each pair of connectors the two links use: `W001` carries the RS-422 link (four wires) and `W002` carries power (two wires). The project is saved. If the project has errors, nothing is saved.

Run the same command again:

```
harness-design-studio generate wheel-link
```

```
0 added, 0 changed, 2 unchanged, 0 removed, 0 frozen (released); 0 locked pin(s) kept
2 interfaces and 6 wires checked: 0 error(s)
```

Generating again keeps the IDs, never touches a released harness, and gives the same bytes for the same design, so Git diffs show real changes only. (A project from an older version that has ten or more shields or segments in one harness shows those harnesses as *changed* once, because the generator now uses the order the files are saved in; after that it is stable.)

**Bad input is reported, not used.** Generation checks `config/*.json` first. A value that is set but impossible (a derating factor above 1, an ampacity table in which a thinner wire carries more, a gauge outside AWG 0 to 40, a negative or fractional pin gap, a number written as text, a wrong `default_gauge_awg` or `wire_colour_by_signal`) is an error in the result and is treated as unset, so the gauge stays *pending*:

```
error: [config_invalid] config/generation.json: default_gauge_awg must be a whole number from 0 to 40.
0 added, 0 changed, 2 unchanged, 0 removed, 0 frozen (released); 0 locked pin(s) kept
2 interfaces and 6 wires checked: 0 error(s)
Not saved: fix the errors above first.
```

Nothing is saved while the result holds errors (exit code 1). A naming pattern that fails, gives a reserved name such as `COM1` or repeats a name is replaced by the default with a warning (`warning: [naming] ...`, see [naming and title block](naming-and-title-block.md)). An interface whose two ends are on one connector, that has fewer than two ends, or whose type repeats a signal name is skipped with a finding (`interface_skipped`) instead of being wired onto one pin. A locked wire or an entered segment length that cannot be carried over to the new plan is named in a warning (`locked_data_lost: W002: W002-001 cannot be carried over and will be lost.`); read it before you apply. A manual harness (one you made by hand, `generated: false`) that takes over an interface makes the generation status *stale*, and deleting a device that a manual harness plugs into is refused.

## 2. Check the result on its own

The tool checks its own result with a second program path that shares no code with the generator. In the app the header of the **Harness** tab shows a chip, *Self-check passed* or *Self-check found n problem(s)* (when design checks failed the chip says so: *Self-check passed; n design checks failed*); hover the chip to read "Self-check: …" and how long it took. (The **Check** step in the top bar is another check: it runs the design rules, see [read and fix problems](read-and-fix-problems.md).) On the command line:

```
harness-design-studio verify wheel-link
```

```
2 interfaces and 6 wires checked: 0 error(s)
```

Exit code 0 means no errors. 1 means the project has errors. 2 means a usage error or a folder that cannot be read.

## 3. Read why a wire is the way it is

In the app, open the **Harness** tab (Ctrl+2; **Drawings** on the rail) and pick a harness, for example `W002`, in the list at the top left.:

- **Connectors and pins** lists every pin with its signal and wire; a pin whose gauge or length is not known yet has a **Pending** chip, and one that the tool chose and nobody has reviewed an **Auto-filled** chip. Spare pins are hidden and counted under the table; **Show spare pins** shows them.
- **Wires** shows each wire with its signal, ends, **Gauge**, **Length**, **Colour** and **Locked** (the **Colour** column in the app is not in the 0.1.0 packages).
- **Why** names the rule behind the wire, connector or pin you select, including gauge and length. This is the tool's answer to "why is it like this?". **Show in Why panel** shows the same in the **Why** tab of the right panel. For a wire or a harness, the tab also has **Show the calculation**: for a wire how its length, the current its gauge may carry, its voltage drop and its share of the mass were made, for a harness how its mass was made, with the equation, every input with its unit and where it comes from, the steps and what it is checked against. It is the same text as `harness-design-studio explain`, and it is closed until you ask for it. Under each calculation a quiet line, for example *Model page: docs/models/wire-sizing.md*, names the page of the documentation that describes the model behind it; it is plain text you can select and copy, and nothing is opened.
- **Drawing** previews the drawing sheet. [Export](export-the-outputs.md) writes it as a PDF only when you ask for the drawings (the check box **Include the PDF drawings**, or `--drawings`). It takes the width and most of the height of the area, with the pin table, the wire table and the reasons under it. The wheel zooms, a drag pans, **Previous sheet** and **Next sheet** page through it, hovering a wire in the drawing or the table marks it in the other, and picking a wire in the drawing selects its link for the Inspector.

Beside **Why** are the tabs **Edit wire**, **Connectors** and **Accessories**, which change the harness: [edit a wire](edit-a-wire.md), [build a harness by hand](build-a-harness-by-hand.md), [enter the build data](enter-the-build-data.md).

On the command line, `harness-design-studio explain DIR WIRE` (or a harness or part ID) prints how the numbers of one wire, one harness, one part or the contacts of an interface at a connector were made: for a wire its length (the segments of its path and the service loops), how its gauge was chosen (the gauges tried, the limit of each after derating and its voltage drop, and the first that passes), the current its gauge may carry after derating, its voltage drop and its share of the mass; for a harness its mass; for a part why the bill of materials has its quantity (connectors, contacts, wires in metres, accessories), and for `INTERFACE.CONNECTOR`, the name of the object of a *Contact current* finding, the limit of the contacts; each with the equation, the inputs with their units and sources, the steps and the assumptions it rests on (add `--json` for data; the last line of the text, and the key `model_page` of the data, name the page of `docs/models/` that explains each kind of number); see [wire length](../models/wire-length.md), [wire sizing](../models/wire-sizing.md) [mass](../models/mass.md) and [bill of materials](../models/bom.md) and [contact current](../models/contact-current.md). `harness-design-studio explain DIR --all --out FOLDER` writes every derivation of the project to `derivations.json` and `derivations.csv` (no time, user or path in them: the same design gives the same files), so that a colleague's result can be checked from the files; see [every derivation as files](../models/README.md#every-derivation-as-files). The reasons that the **Why** pane shows are also stored in `generated/generation.json` in the project, under `provenance`.

## How links become harnesses

By default one harness is made for each pair of device connectors. The setting is in `config/segmentation.json`:

```
{
  "name": "segmentation",
  "placeholder": true,
  "values": {
    "mode": "per_connector_pair"
  }
}
```

| `mode` | One harness for each ... |
| --- | --- |
| `per_connector_pair` (default) | pair of device connectors |
| `per_unit_pair` | pair of devices |
| `per_zone_pair` | pair of zones (links between the same two lanes) |

With the `minimal-satellite` example (11 links), the default makes 11 harnesses. After changing `mode` to `per_unit_pair` and running `harness-design-studio generate` again, the report is `1 added, 9 changed, 0 unchanged, 2 removed`: ten harnesses replace the eleven. Harnesses that keep a pair of devices keep their IDs (here `W001`, `W002` and `W005` to `W011`, nine of them changed), the new one gets the next free ID (`W012`), and the files of the old ones stay in `physical/harnesses/` with the ending `.json.bak`. A second run changes nothing. (`minimal-satellite` is not in the 0.1.0 packages; see the [changelog](../../CHANGELOG.md).)

Whatever the mode:

- Nominal and redundant chains never share a harness, and pyro lines (firing circuits) never share a harness with other lines.
- This rule is a placeholder until the owner decides it (decision D-10 in [`DECISIONS.md`](../DECISIONS.md)). The file keeps `"placeholder": true`.
- A link between **more than two devices** (a bus) is not generated yet (D-116). It is skipped with the note "multi-drop interfaces (more than two devices) are not generated yet".

The file has a wrapper: the setting is under `values`. A key at the top level is refused. See [fill in the engineering values](fill-in-engineering-values.md#the-shape-of-a-config-file).

## How auto-linking and the checks work

This section follows one design from the devices to a checked harness. At each step it says what the tool does by itself and what you decide. Three words matter here: an **interface** (`IF-002`) is a connection of a type, for example RS-422, that you ask for between two devices; a **connection** (`L7`) joins two connectors pin by pin; a **harness** (`W001`) is the cable the tool makes. How these IDs are made and where you see them: [connector IDs and tags](naming-and-title-block.md#connector-ids-and-tags).

| Step | What the tool does by itself | What you decide |
| --- | --- | --- |
| 1. Devices | Gives each device an ID, and each of its connectors an ID made from the device ID (`PCDU1`, `PCDU1-J01`). A KiCad import puts the signal names on the pins and marks those pins *fixed*. | Which devices there are, their connectors and parts, and their pinouts ([define a device](define-a-device.md), [import KiCad pinouts](import-kicad-pinouts.md)). |
| 2. Interfaces | When you connect two devices with an interface type, it picks at each device the first free connector that carries the type (when none is free, a connector with a free port of the type, since 2.1.0), and marks the choice *auto-filled*. | The type and the two devices. You confirm the connectors, or choose others in Expert mode. |
| 2a. Connections, pin by pin | In the window *Link connectors* it proposes pairs of pins from the signal names (`TX+` with `RX+`, `PWR` with `PWR`), never from the pin numbers. | You read the pairs, change them, and press **Apply**. A harness is made from a connection only when you press **Create harness**. |
| 3. Generate | Groups the interfaces into harnesses (one for each pair of device connectors by default), and makes the cable connectors, the pins and the wires. | You press **Generate**, read the preview and press **Apply**. The grouping is a setting ([above](#how-links-become-harnesses)). |
| 4. Pins | Fills a fixed pin by its name, and gives each interface the pins of one port when the names name ports (since 2.1.0). Gives free pins to signals with the pin allocator: power first, then the other signals, each group on the first free pins. | You can lock a pin, fix a pinout, or change the order and the gaps in the settings. |
| 5. Checks | Runs the quick checks on every edit, the design rules a moment after you stop editing, and the self-check on the harnesses. | You fix a finding, waive a warning with a reason, or enter the missing values. The tool does not waive or approve anything. |

### 1 and 2: devices, interfaces and auto-filled connectors

Each new device gets an ID from its kind (`PCDU1`, `OBC1`) and connectors named `<device>-J01`, `<device>-J02`, and so on. When you connect two devices with an interface type, the tool looks at the connectors of each device in ID order and takes the first free one that carries the type. It writes `"auto": true` on that end of the interface, the diagram marks it *auto-filled*, and the design rules list it until a person confirms it:

```
harness-design-studio drc wheel-link
```

```
- **IF-001 uses connectors the tool chose for you** (`unconfirmed.IF-001`)  
- **IF-002 uses connectors the tool chose for you** (`unconfirmed.IF-002`)  
```

Confirm them with **Confirm auto-filled connectors** in the Inspector of the link, or with the fix button of the card ([read and fix problems](read-and-fix-problems.md#2-in-the-app)). `harness-design-studio explain wheel-link RW1-J02` prints why a connector was taken: *Connectors of RW1 that carry rs422: in ID order: RW1-J02; the tool takes the first one that is free*. The order can be changed with the setting `model.connector_choice` ([pin allocation](../models/pin-allocation.md#the-choice-of-a-connector)).

**Several interfaces on one connector.** A device connector can carry several interfaces (since 2.1.0, decisions D-233 and D-237 in [`DECISIONS.md`](../DECISIONS.md)). In Expert mode you can connect another interface to a connector that already carries some, as long as it has room. The tool decides the room with the same pin assignment that Generate uses, so the two always agree. A full connector is refused with the reason, for example *RW1-J02 cannot take another RS-422: too few free pins for TX+, TX- (1 free, 2 needed)*. In Guided mode the tool first takes a free connector, as before. Only when no connector is free does it take a connector with a fixed pinout that has a free complete port of the type (pins named `RS422_2_TX+` ...). It never shares a connector whose pins the device leaves free.

The editor adds a note in two cases. When the connector's other interfaces go to another far connector, Generate makes a second harness with its own plug on the connector and warns (`box_connector_shared`), until a harness can branch (planned for 2.3.0). The [worked example](#worked-example-three-rs-422-links-on-one-connector-since-210) shows it, and how to avoid it. When a released harness plugs into the connector, the new interface is wired only after a new revision of that harness ([change a released harness](change-a-released-harness.md)). The note shows in the tooltip while the pointer is over the connector, in the message after you connect, and in the tooltip of the connector in the Inspector's list of an end.

**On screen** (since 2.1.0):

- **The diagram.** In Expert mode a connector in use that has room lights up like a free one. A full one stays grey; a click on it says why. A connector that carries several interfaces is drawn on the side of the first interface on it, by ID.
- **The Inspector of an interface.** The list of an end offers the shared connectors with room. A full connector is listed as *J1: Full*, not offered, with the reason in its tooltip. On a fixed pinout with named ports each end has a line such as *Port RS422_2 (pins 5-8), chosen by Generate*. It says *locked* when a person chose the port, and *Generate will choose it* before Generate has run. **Choose port…** opens a short list of the complete ports of the connector; a port that cannot be taken says why. The choice locks the port's pins to the interface in one undo step (*Assign port RS422_3 to IF-012*). The next Generate keeps the interface on that port.
- **The Inspector of a device** (Expert mode) has one **Confirm** for each interface the tool chose a connector for. When one connector was chosen for several interfaces, each button names its interface (*Confirm IF-012*).

**A bus** (one interface between more than two devices) is not generated yet (D-116).

### 2a: connections made pin by pin

A connection does not need an interface type. In the window *Link connectors* the tool proposes pairs from the signal names: equal names (`PWR` with `PWR`, `CANH` with `CANH`) and the two ends of one line (`TX+` with `RX+`, words set in `naming.signal_counterparts`). It never pairs by position, unless you press **Pair by pin number**. Nothing is saved until you press **Apply**, and a harness is made only when you press **Create harness**. **Design > Check my connections** reviews the pairs and changes nothing ([connect two connectors](connect-two-connectors.md)).

### 3: from interfaces to harnesses

**Generate** reads every interface and makes one harness for each pair of device connectors (the setting `segmentation.mode`). For each device connector it makes a cable connector of the mating part, and for each signal of the interface a wire between the two cable connectors. A harness made by hand, a released harness and a locked wire are left as they are ([keep a choice of your own](#keep-a-choice-of-your-own)). The preview says what would be added, changed and removed before anything changes.

### 4: pins, fixed by name or given by the allocator

On each device connector the tool decides which pin carries which signal:

- **A fixed pin** (a pinout from KiCad, or a pin you marked *fixed*) is filled **by its name**. The signal `RX+` of an interface goes to the free pin whose signal name is `RX+` (pin 3 of `RW1-J02` with the practice netlist). If no such pin is free, generation stops with an error for that interface and does not use another pin ([what "fixed" means](import-kicad-pinouts.md#what-fixed-means)).
- **A free pin** is given by the **pin allocator**. Power and ground come first, as one block, then the other interfaces in the order of their IDs. Each group (a pair, a power block, a single signal) takes the first free run of pins. A locked pin stays where it is, and an earlier choice is kept while it is still valid ([pin allocation](../models/pin-allocation.md)).

You can see which of the two applied to a pin. After the KiCad import of [import KiCad pinouts](import-kicad-pinouts.md) and a new `generate`:

```
harness-design-studio explain wheel-link RW1-J02.3
```

```
Pin 3 of RW1-J02. Pin allocation: RX+ of IF-002 on pin 3
...
    Pin is locked = no   [pin 3: Locked (a locked pin is never moved)]
    Pinout is fixed by the device design = yes   [pin 3: Fixed (a fixed pinout gives the signal the free pin of its name)]
...
```

Without the import the same line says `Pinout is fixed by the device design = no`, and the pin was chosen by the allocator. The **Why** tab of a pin shows the same text.

**A connector with several ports** (since 2.1.0). On a fixed pinout whose pin names name ports (`RS422_1_TX+`, `RS422_2_TX+` ...), each interface gets the pins of one port, all or nothing, and the pins of two ports are never mixed. A port you chose with **Choose port…** comes first, then the port the interface had at the last Generate, then the pins of the bare signal names (as in 2.0.1), then the first free complete port in name order (`RS422_2` before `RS422_10`). The full rule is in [pin allocation](../models/pin-allocation.md#ports-on-a-fixed-pinout). When the pins carry the bare names more than once (`TX+` three times) and several interfaces of the type need them, the tool cannot tell which pins form one port: it keeps the assignment of 2.0.1 (each signal takes the first free pin of its name, interfaces in ID order) and warns with `pin_port_unknown`. Name the ports, or lock the pins of each port.

### Worked example: three RS-422 links on one connector (since 2.1.0)

An on-board computer OBC1 talks to three star trackers over RS-422, and all three links leave on its one connector J1. The pinout of J1 names a port for each link.

Make an empty project for the example first:

```
harness-design-studio new obc-demo --template blank
```

1. **Import the pinout of OBC1** with a *Port* column (or with names such as `RS422_2_TX+` and no Port column; both give the same pins):

   ```
   Connector,Pin,Port,Signal,Mode
   J1,1,RS422_1,TX+,fixed
   J1,2,RS422_1,TX-,fixed
   …
   J1,12,RS422_3,RX-,fixed
   ```

   Save it as `obc1.csv` (all twelve rows are in [define a device](define-a-device.md#a-connector-with-several-ports-since-210)), then:

   ```
   harness-design-studio import-pinout obc-demo obc1.csv --device OBC1 --new-device "On-board computer" --default-part EX-MICROD-25-F
   ```

   ```
   …
   OBC1-J01: OK added (12 pin(s))
   OBC1-J01: Ethernet or RS-422 ports: RS422_1 (pins 1-4), RS422_2 (5-8), RS422_3 (9-12)
   Imported 1 connector(s), 12 pin(s).
   …
   ```

   Import the three star trackers STR1, STR2 and STR3 the same way, each with one connector whose pins are `TX+`, `TX-`, `RX+` and `RX-` ([define a device](define-a-device.md#a-connector-with-several-ports-since-210)). With a file `str.csv` that has the columns *Pin*, *Signal* and *Mode* and these four pins, fixed:

   ```
   harness-design-studio import-pinout obc-demo str.csv --device STR1 --new-device "Star tracker 1" --default-part EX-MICROD-9-F
   ```

   Then the same for STR2 and STR3. `EX-MICROD-9-F` is a part of the library of the blank template.

2. **Connect OBC1 to each star tracker** in the editor: there is no command to add an interface. Open `obc-demo` (**File > Open project**) and connect OBC1 to STR1, STR2 and STR3 in turn with the type RS-422, in Guided mode (**Ctrl+I**, or a cable dragged from OBC1 to the star tracker). Then save. The first link takes J1, the only free connector of OBC1. J1 is not free for the second and the third, so the tool takes it again because it has a free complete port. In the Inspector the end of IF-002 at OBC1 says *Port RS422_2 (pins 5-8), Generate will choose it*.

3. **Generate** (in the editor, or `harness-design-studio generate obc-demo`). IF-001 gets port RS422_1 (pins 1-4), IF-002 gets RS422_2 and IF-003 gets RS422_3: ports in name order, interfaces in ID order. The default segmentation makes one harness per pair of device connectors, so each link gets its own harness with its own plug on J1, and Generate warns:

   ```
   warning: [box_connector_shared] OBC1-J01 has more than one cable plug on it: W001-P1 (W001), W002-P1 (W002), W003-P1 (W003). A connector takes one plug; two harnesses cannot both plug into it. Give the interfaces that share it one harness, or use different connectors.
   3 added, 0 changed, 0 unchanged, 0 removed, 0 frozen (released); 0 locked pin(s) kept
   3 interfaces and 12 wires checked: 0 error(s)
   ```

   The design rules report the same as `model-inconsistent` (*The device connector OBC1-J01 has 3 cable plugs on it*). A real connector takes one plug. Until a harness can branch (planned for 2.3.0, decision D-235), give the three links one harness: set `segmentation.mode` to `per_zone_pair` and put the three star trackers in one zone (one lane of the diagram). Generate then makes one harness W001 with one plug on J1 and one on each star tracker, and the warning and the finding go away ([how links become harnesses](#how-links-become-harnesses)).

4. **Check.** `harness-design-studio verify obc-demo` says `3 interfaces and 12 wires checked: 0 error(s)`. `harness-design-studio export obc-demo` writes the outputs. Then `obc-demo/outputs/system/box_pinouts.csv` lists each pin with its port name and its interface (`OBC1-J01,box,,EX-MICROD-25-F,5,RS422_2_TX+,IF-002,W002-001,no`). `harness-design-studio explain obc-demo OBC1-J01.5` names the port: *Port of the pin: RS422_2_TX+ is the TX+ of port RS422_2 of OBC1-J01; …*. `harness-design-studio explain obc-demo OBC1-J01` gives the choice of the connector in one step for the three links: *Connectors of OBC1 that carry rs422, for IF-001, IF-002, IF-003: in ID order: OBC1-J01; the tool takes the first one that is free, else the first with a free complete port of the type* (since 2.1.1; 2.1.0 gave the step once per link without naming it). A second Generate changes nothing.

5. **Choose a port yourself** when the wiring must follow another plan, say IF-003 on RS422_1. In the Inspector of IF-003, **Choose port…** on the end at OBC1 lists *RS422_1 (pins 1-4)*, *RS422_2 (pins 5-8)* and *RS422_3 (pins 9-12)*. Once Generate has run, a port that another interface holds says why it cannot be taken (*Pin 1 carries IF-001; unassign it first.*), so choose before you generate, or first free those pins with **Unassign from interface** in the **Devices** tab. Pick RS422_1: its pins become *Locked* to IF-003 in one undo step, and the pins Generate gave IF-003 before are freed in the same step. The next Generate keeps IF-003 on RS422_1 and gives IF-001 and IF-002 the free ports in name order, RS422_2 and RS422_3. **Assign…** with its **Port** list in the **Devices** tab does the same.

6. **When J1 is full**, a fourth link cannot use it. In Expert mode, connecting to it is refused with the reason (*OBC1-J01 cannot take another RS-422: its RS-422 ports RS422_1, RS422_2, RS422_3 are used by IF-001, IF-002, IF-003.*), and the Inspector's list of connectors shows it as *J1: Full* when the interface has another connector to choose. In Guided mode a fourth RS-422 link to OBC1 is refused with *OBC1 has no free RS-422 connector. Use a device template that has one …*; this message does not name the ports. Add a connector, or add a port to the pinout.

### 5: when the checks run

| Check | When it runs | Where you see it |
| --- | --- | --- |
| **Quick checks** (a link without a connector, a device with no link, auto-filled connectors, a link across the chains) | On every edit, at once. | The **Problems** tab and the marks on the diagram. |
| **Design rules** (all 39, [`RULES.md`](../RULES.md)) | In the editor, by themselves, after every change, once you have paused for **1.2 seconds**, and when a project is opened. They run in a separate helper process, so the editor does not wait. A run that does not end within three minutes is stopped and run again inside the editor. **Check** in the top bar (F5) runs them now. | The status line (*Design rules: checking…*, then the counts), the **Checks** tab and the **Problems** panel ([read and fix problems](read-and-fix-problems.md)). |
| **Self-check** (a second program path that shares no code with the generator) | In the editor, in the background, when the **Harness** tab is open and the design changed, and again after an export. On the command line at the end of every `generate`. | The chip in the header of the **Harness** tab: *Self-check passed*, *Self-check passed; n design checks failed* or *Self-check found n problem(s)*. |
| **Output check** | Before `export` writes any file. | If it fails, nothing is written and the reason is shown ([export the outputs](export-the-outputs.md#1-export)). |

On the command line you choose which check runs:

| Command | What it checks | Exit code 1 when |
| --- | --- | --- |
| `harness-design-studio validate DIR` | That the folder is sound: errors and inconsistencies in its files. No design rules. | an error is found |
| `harness-design-studio check DIR` | The same as `validate`, plus what a Git merge can leave behind ([use Git and CI](use-git-and-ci.md)). | an error is found |
| `harness-design-studio drc DIR` | The 39 design rules, with the report. | an error is not waived |
| `harness-design-studio verify DIR` | The self-check of the harnesses against the design; `--outputs` also checks the written files. | an error is found |

With the practice project after `generate`:

```
harness-design-studio check wheel-link
```

```
INFO    placeholder_config: Placeholder rule configuration still in use: derating, emc, generation, segmentation, segregation, titleblock. An engineer must review these before results are trusted.
3 devices, 2 interfaces, 13 connectors, 2 harnesses: 0 error(s), 0 warning(s).
```

```
harness-design-studio drc wheel-link
```

```
# Design rule check: First steps: reaction wheel link

Model hash: `<hash>`. Rules run: 39.
Open: 0 error(s), 10 warning(s), 8 note(s). Waived: 0.
```

**What the checks do not decide.** A rule that needs a value nobody has entered says *not checked*, never *passed*. A clean report means that the tool found nothing it can check; it does not mean that the harness is right. The person who builds and flies it checks it ([using HDS in your organisation](use-hds-in-your-organisation.md#what-you-must-verify)).

## Keep a choice of your own

Generation may change a wire or a pin you edited. To keep a value, lock it.

- **A wire, in the app (since 1.4.0):** select it in the **Drawings** area and set its gauge, type, colour or length in the **Edit wire** tab. That locks the wire: Generate keeps those values, and **Reset to generated** hands it back. A label, a note and the strip lengths are always kept (they do not lock the wire), a wire you draw yourself is kept as it is, and so are the groups you make ([edit a wire](edit-a-wire.md)). If Generate cannot keep something (its interface is gone) it says so with the finding `locked_data_lost`. The same holds for the accessories of a harness (kept while the connector or wire they sit on is kept) and the contact of a pin, which Generate copies from the pin of the device to the cable connector ([enter the build data](enter-the-build-data.md)).
- **Many wires, in the app (workshop milestone M3):** **Edit all wires…** sets the gauge, type, colour and length of all wires of the harness, the selected ones or those of one signal in one step; they are locked exactly as an edited wire ([edit a wire](edit-a-wire.md#10-edit-all-wires)).
- **A connector of a generated harness (M3):** in the **Connectors** tab, change its part, gender or keying, or the signal, role, function, termination or contact size of a pin. The connector then belongs to you (`"locked": true` in its entry of `physical/harnesses/<ID>.json`): Generate keeps those values, while the name, the pins and the contact of each pin keep following the device. **Give back to Generate** hands it back; if the device connector is gone, `locked_data_lost` names it ([build a harness by hand](build-a-harness-by-hand.md#change-a-connector-and-its-pins)).
- **A group you made (M3):** **Change group…** changes its kind, wires and shield ends; Generate keeps the group ([edit a wire](edit-a-wire.md#9-change-a-group)).
- **A pin, in the app:** the *Mode* column of the **Devices** tab: *locked* keeps the pin where it is, *fixed* also fixes its signal. The report counts them: "0 locked pin(s) kept".
- **In the file:** a wire's entry in `physical/harnesses/<ID>.json` with `"locked": true` does the same as the Edit wire tab; a pin's entry with `"locked": true` the same as the Devices tab. A locked pin that already carries a signal stays where it is on a connector with a fixed pinout, and a locked fixed pin keeps its interface. In `per_unit_pair` mode a renamed device keeps its harness IDs, locked wires and lengths when the interfaces stay the same.

This was checked on the command line with `first-steps`: a wire set to gauge 20 and colour `red` with `"locked": true` kept both after `harness-design-studio generate`, and a wire set to gauge 20 without the lock went back to the tool's own value (here no gauge, because the derating values are still placeholders). Edit the file only while the project is not open in the app. If it is open, the app reports "Project changed on disk" and offers to reload.

## Common mistakes

- **"there are no harnesses to export; run `harness-design-studio generate` first."** You have not generated yet, or the project has no links. Generate first. (A project whose connections were made with **Link connectors…** exports without a harness: it gets the connection list, `system/connections.csv` and `.xlsx`.)
- **A blank project generates nothing.** The command line has no command to draw a single device or link by hand (devices come in from a file with `import-pinout --new-device`, `import-devices` or `import-subsystem`). Draw devices and links in the app ([draw the design](draw-the-design.md)), or start from an example. A harness made by hand with **New harness…** is left alone by Generate.
- **Gauge says *pending*.** Not a fault. A value is missing: run `harness-design-studio config DIR` ([fill in the engineering values](fill-in-engineering-values.md)). The power link also needs its **Max current (A)**.
- **"The model changed after the harness plans were generated."** You changed the design after generating. Generate again.

More: [`TROUBLESHOOTING.md`](../TROUBLESHOOTING.md).

Next: [read and fix problems](read-and-fix-problems.md), [fill in the engineering values](fill-in-engineering-values.md), [export the outputs](export-the-outputs.md)
