# Pin allocation and the choice of a connector

This page explains why a signal is on a pin of a device connector, and why a connector is the connector of an interface. It is written from what the program does (`core/generate/pins.py`, `core/ports.py`, `core/checks.py`), and the examples come from the `flatsat` example, where you can repeat them with `harness-design-studio explain DIR MTQ1-J01.1` (a pin) and `explain DIR GPSU1-J01` (a connector).

## Contents

- [What the tool decides](#what-the-tool-decides)
- [The order](#the-order)
- [Ports on a fixed pinout](#ports-on-a-fixed-pinout)
- [The inputs and where they come from](#the-inputs-and-where-they-come-from)
- [The assumptions it rests on](#the-assumptions-it-rests-on)
- [A worked example](#a-worked-example)
- [A worked example with ports](#a-worked-example-with-ports)
- [The choice of a connector](#the-choice-of-a-connector)
- [What happens when a value is missing](#what-happens-when-a-value-is-missing)
- [What the model does not do](#what-the-model-does-not-do)

## What the tool decides

When harnesses are generated, every signal of an interface gets a pin of the device connector at each end. `explain DIR CONNECTOR.PIN` (or the Why tab of a pin, a wire or an interface) gives a derivation of kind `pin-allocation` for the pin: what is on it and why, from the order of the categories, the gaps, the locks and the lines the generator recorded when it ran. The cable end of a connector has the same pin numbers, so asking for a pin of the cable connector explains the pin of the device connector it plugs into.

## The order

On one device connector the interfaces are placed in this order:

1. The categories listed in `model.pin_allocation_categories`, in the order listed (power, then ground, by default). They count as the *power group*: the signals of one interface are kept together as one block, with `power_return_gap_pins` unassigned contacts between them, and the first signal pin comes after `power_signal_gap_pins` free pins.
2. Every other category, by interface ID inside a category.

Inside that order each group of signals (a pair, a power block, a single signal) takes the **first free run of pins** in the order of the pin list, starting after the gap (this is the strategy `first_fit`; the setting `model.pin_fit_strategy` can choose `last_fit`, which fills from the last pin down, or `spread`, which leaves a free pin between interfaces, and `explain` names the one in force). A pair sits on neighbouring pins. Three things override the order:

- a pin that is **locked** is never moved, and a pin held by a released harness stays;
- a connector with a **fixed pinout** (the device design names every pin) gives each signal the free pin of its name, or the pins of one port (see below);
- an earlier allocation is **kept** while it is still valid, so a small change makes a small difference.

## Ports on a fixed pinout

A connector with a fixed pinout can carry several interfaces of one type, one on each **port**. A port is part of the signal name of a pin (decision D-237): `RS422_2_TX+` is the signal TX+ of the port RS422_2. The prefix form `PORT<sep>SIGNAL` and the suffix form `SIGNAL<sep>PORT` are read, with the separator `_`, `.` or `-`. A pin named only by the signal (`TX+`) belongs to no named port. A port can be used when it has exactly one pin for each signal of the type.

On such a connector each interface gets the pins of one port, all or nothing:

1. An interface whose locked pins are in a port takes its other signals from that port. When the port has no free pin for a signal, Generate stops with an error that names the port and the signal. Locked pins in two ports are an error too. The pins of two ports are never mixed.
2. An interface gets back the port it used at the last Generate, while that port is still free. So a second Generate changes nothing.
3. Every other interface takes the free pins of the exact signal names, as 2.0.1 did. When they hold every signal, nothing changes: a project that generates at 2.0.1 generates the same.
4. An interface that step 3 cannot place takes the first free complete port, in the order a person reads the names (`RS422_2` before `RS422_10`). Interfaces go in the order of their category, then by ID.

A port that misses a signal or has two pins for one signal is not used; when no port is free, the error says why for each port (*port RS422_3 has no pin for RX-*). The explanation of a pin names its port: *TX+ of IF-012 uses pin 5, the TX+ of port RS422_2 of OBC1-J1; an interface keeps the port it used before, else takes the first free RS-422 port (ports in name order, interfaces in ID order)*. `explain DIR CONNECTOR.PIN` adds the step *Port of the pin*.

**A port chosen by a person.** *Choose port…* in the Inspector, or *Assign…* with its *Port* list in the Devices tab (`devices.ops_assign_port`), locks the pins of one complete port to the interface: `locked` and `interface_id` are set, the signal names and `fixed` stay. In the same undo step the pins of that connector that Generate gave the interface before (not locked, not in the new port) lose the interface; nothing else of them changes. A port is refused when it is incomplete or doubled, when a release locks one of its pins, or when another interface holds one of them. Step 1 above then keeps the interface on that port at every Generate.

When two or more interfaces of one type need signal names that repeat on a connector (`TX+` on two pins), the tool cannot tell which pins form one port. It keeps the assignment of 2.0.1 and adds the warning `pin_port_unknown`: name the ports (`P1_TX+`, `P2_TX+`) or lock the pins of each port.

The design rules `signal-unassigned` and `direction-conflict` read the signal of a port pin, and so does the independent verifier. The verifier reports `port_mixed` when one interface uses the pins of two ports of one connector.

Ports and harnesses are separate decisions. The ports decide the pins on the device connector; the segmentation decides how many harnesses plug into it. With the default `per_connector_pair`, interfaces from one connector to different far connectors get a harness each, so the connector gets one plug per harness and Generate warns `box_connector_shared` (the design rule `model-inconsistent` reports it too). `per_zone_pair` with the far devices in one zone puts them into one harness with one plug on the connector ([segmentation](segmentation.md)). A harness that branches from one plug to several far connectors is planned for 2.3.0 (D-235).

## The inputs and where they come from

| Input | Source |
| --- | --- |
| The signal and interface on the pin | The device connector (the generated assignment, or a typed one). |
| The category of the interface | The interface type. |
| The order of the categories | `config/model.json: pin_allocation_categories` (default `power, ground`). |
| The pin fit strategy | `config/model.json: pin_fit_strategy` (default `first_fit`). |
| Pins between power and signal | `config/generation.json: power_signal_gap_pins` (0 is used, as a placeholder, while it is not set). |
| Contacts between power and return | `config/generation.json: power_return_gap_pins` (ECSS-Q-ST-30-11C requirement 0140052 is cited by ID). |
| Locked, fixed | The pin. |
| The port of a fixed pin | The pin's signal name (`RS422_2_TX+`), read by `core/ports.py`; the interface type's signal names. No field holds it. |
| The lines recorded when it was generated | The Why tab (`core/why.py`): the derivation quotes them and does not repeat them. |

## The assumptions it rests on

- **A-PIN-ORDER.** The order of the categories and the gaps are settings.
- **A-PIN-FIRST-FIT.** First fit in the order of the pin list (the default of the setting `model.pin_fit_strategy`; `last_fit` and `spread` are the alternatives, see [selectable models](selectable-models.md#pin-fit-strategy)); an earlier choice is kept while it was made by the same strategy; locks and fixed pinouts win. On a fixed pinout the ports are taken in name order. Neighbours are neighbours in the list of pins, not a measured position.

## A worked example

`harness-design-studio explain DIR MTQ1-J01.1` on the `flatsat` example prints **PWR of IF-018 on pin 1**. The interface type `power_primary` has the category `power`, which is the first of the listed categories; the pin is the first of a block of two (PWR and RTN, *power and return grouped*); nothing lies ahead of it. The recorded line is *pin-allocation: PWR of IF-018 (power and return grouped)*. The gaps are 0 (`power_signal_gap_pins` is not set, a placeholder).

## A worked example with ports

An on-board computer OBC1 has one connector OBC1-J01 with twelve fixed pins `RS422_1_TX+` ... `RS422_3_RX-`, imported with a Port column. Three RS-422 interfaces IF-001 to IF-003 go from OBC1 to three star trackers. The tool chose OBC1-J01 for IF-001 because it was free, and for IF-002 and IF-003 because it had a free complete port (the second tier of the choice below). Nothing is locked, and no earlier Generate exists. Step 3 places no interface (the bare names `TX+` ... are not on the connector), so step 4 gives each interface the first free complete port: IF-001 RS422_1, IF-002 RS422_2, IF-003 RS422_3. `explain DIR OBC1-J01.5` prints **RS422_2_TX+ of IF-002 on pin 5** and the step *Port of the pin: RS422_2_TX+ is the TX+ of port RS422_2 of OBC1-J01; the pins of one port go to one interface (ports in name order, interfaces in ID order) = port RS422_2*. A second Generate gives every interface the port it had (step 2) and changes nothing. With IF-003 locked to RS422_1 beforehand, IF-003 keeps RS422_1 (step 1), and IF-001 and IF-002 take RS422_2 and RS422_3. The user manual follows the same case on screen: [three RS-422 links on one connector](../user-manual/generate-harnesses.md#worked-example-three-rs-422-links-on-one-connector-since-210).

## The choice of a connector

A connector is chosen for an interface at a device by a person, or by the tool. When the tool chooses, it takes the **first free connector** of the device (in ID order) that carries the interface type (the default; `model.connector_choice` can choose `fewest_spare_pins`, the best fit, or `most_spare_pins`, see [selectable models](selectable-models.md#connector-choice), and `explain` shows the one in force), and the choice is marked *chosen by the tool, not confirmed* until a person confirms it (the finding `unconfirmed`). Only when no connector is free does the tool take a connector with a fixed pinout that has a free complete port of the type. `explain DIR CONNECTOR` shows which connectors of the device carry the type and which was taken (kind `connector-choice`); with another model in force it lists every interface on each candidate and its free ports.

A connector can carry several interfaces (since 2.1.0, D-237). Whether it takes one more is decided by a dry run of this pin allocation with every interface that ends on the connector and the new one. The connector is full when the new interface gets no pins, or when it would take the pins of an interface that has them now. The editor refuses a full connector with the reason, for example *J01 cannot take another RS-422: its RS-422 ports RS422_1, RS422_2 are used by IF-010, IF-011*.

The **cable end** of a device connector is the part the library names as its mating part (`mates_with` of the device connector's part); a part with none is mated with itself, and generation says so. The gender is the opposite of the device connector's and the keying is copied. A cable connector that a person edited keeps its part, gender and keying.

- **A-CONNECTOR-CHOICE.** First free connector that carries the type (the default of the setting `model.connector_choice`; the alternatives are best fit and most spare pins); only when none is free, a connector with a fixed pinout and a free complete port of the type; the cable end is the mating part.
- **A-PORTS.** A connector takes another interface while the dry run of the pin allocation has room for it. On a fixed pinout the pins of one port are named by the port and the signal (`RS422_2_TX+`); an interface uses the pins of one complete port, never of two. Interfaces from one connector to different far connectors get a harness each, with two plugs on the connector, until a harness can branch.

## What happens when a value is missing

The gaps and the order always have a value (a default or a placeholder, named in the source of the input). A pin or connector that does not exist gives a derivation with no result that names it as missing.

## What the model does not do

- It does not replay the allocator. The pin is explained from what the generator left in the design and recorded, so a design edited by hand after generation is explained as it is now. A setting changed after generation changes the explanation of the order, not the pin, until the harnesses are generated again.
- It does not choose the connector part of a device: that is the device design or the library.
- It does not know the position of a pin on the connector face.
- It does not read a port from a free pin, from a pin name that reads in two ways, or across two connectors: a port is the fixed pins of one connector whose names name it.
- It does not check that a connector carrying a noisy and a sensitive interface keeps them apart: the EMC rules look at a harness, not at the pins of one connector.

Next: [segmentation](segmentation.md), [the models](README.md), [what the tool assumes](../user-manual/see-what-the-tool-assumes.md)
