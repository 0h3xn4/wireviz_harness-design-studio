# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# ruff: noqa
# mypy: ignore-errors
"""The current rules exactly as release 4.4.0 had them: a verbatim copy of the part of
`core/drc/rules.py` from `# ---- ratings` to the end of `_unchecked` (`current-over-contact`,
`current-over-wire`, `voltage-drop`, the notes of `unchecked-config` that read a current, among them
`_wires_without_interface`) and of `_bundle_current` with its helpers of `core/drc/standard_rules.py`,
at e6eddc0, the tag `v4.4.0`; only the imports are written here. Release 5.0.0 takes the current of a
wire from the pin currents of its net (design `docs/ait/DESIGN_5.0_FORMAT_5.md`, part B, section
11 (2)); `tests/test_currents_compat_440.py` compares the rules of the current core with these on
random projects with no pin current (Hypothesis): every finding must be identical. Do not edit this
file."""

from collections.abc import Iterator

from harness_design_studio.core import settings
from harness_design_studio.core.configcheck import validate as validate_config
from harness_design_studio.core.drc.base import Hit, cfg, flag, number
from harness_design_studio.core.drc.electrical import unchecked as electrical_unchecked
from harness_design_studio.core.drc.standard_rules import unchecked as standard_unchecked
from harness_design_studio.core.generate.bundle import BASIS_TEXT, basis, bundle_size
from harness_design_studio.core.generate.lengths import wire_length
from harness_design_studio.core.generate.sizing import (
    ampacity_table,
    bundle_k,
    exceeds,
    voltage_drop_v,
    wire_current_limit,
)
from harness_design_studio.core.model import Connector, Harness, InterfaceInstance, Project, Wire
from harness_design_studio.core.vcs.consistency import release_integrity


def _wire_interfaces(project: Project, h: Harness) -> set[str]:
    return {w.interface_id for w in h.wires if w.interface_id} | set(h.interfaces)


# ---- ratings ---------------------------------------------------------------------------------------


def contact_rating_key(project: Project) -> str:
    """The key of `Part.ratings` that holds the current a contact of the connector part may carry."""
    return str(cfg(project, "derating").get("contact_rating_key") or "contact_current_a")


def contact_rating(project: Project, conn: Connector) -> float | None:
    part = project.parts.get(conn.part_id)
    return part.ratings.get(contact_rating_key(project)) if part else None


def _bundle_table_given(d: dict[str, object]) -> bool:
    """The table of bundle factors replaces the single factor (as in sizing)."""
    return isinstance(d.get("bundle_factor_by_count"), dict) and bool(
        d.get("bundle_factor_by_count")
    )


def _derated_limit_ready(project: Project) -> bool:
    d = cfg(project, "derating")
    return (
        ampacity_table(d.get("ampacity_a_by_awg")) is not None
        and (number(d.get("bundle_derating")) is not None or _bundle_table_given(d))
        and number(d.get("temperature_derating")) is not None
    )


def _current_over_contact(project: Project) -> Iterator[Hit]:
    factor = number(cfg(project, "derating").get("contact_current_factor"))
    if factor is None:
        return
    for i in sorted(project.interfaces.values(), key=lambda x: x.id):
        if i.max_current_a is None:
            continue
        for e in i.endpoints:
            conn = project.connectors.get(e.connector_id or "")
            rating = contact_rating(project, conn) if conn else None
            if (
                conn is not None
                and rating is not None
                and exceeds(i.max_current_a, rating * factor)
            ):
                yield Hit(
                    f"{i.id}.{conn.id}",
                    f"{i.id} carries {i.max_current_a:g} A but contacts of {conn.id} allow {rating * factor:g} A after derating",
                )


def _wire_current_limit(project: Project, w: Wire, h: Harness | None = None) -> float | None:
    """Ampacity of the wire's gauge after derating (`sizing.wire_current_limit`, the limit that
    `bundle-current` and the wire sizing use too)."""
    return wire_current_limit(
        cfg(project, "derating"), w.gauge_awg, bundle_size(project, h, w) if h is not None else None
    )


def _current_over_wire(project: Project) -> Iterator[Hit]:
    for h in sorted(project.harnesses.values(), key=lambda x: x.id):
        for w in h.wires:
            i = project.interfaces.get(w.interface_id or "")
            limit = _wire_current_limit(project, w, h)
            if (
                i
                and i.max_current_a is not None
                and limit is not None
                and exceeds(i.max_current_a, limit)
            ):
                yield Hit(
                    w.id,
                    f"Wire {w.id} (AWG {w.gauge_awg}) carries {i.max_current_a:g} A but allows {limit:g} A after derating",
                )


def _voltage_drop(project: Project) -> Iterator[Hit]:
    limit = number(cfg(project, "derating").get("max_voltage_drop_v"))
    rho, _missing = settings.resistivity(project)
    if limit is None or rho is None:
        return
    for h in sorted(project.harnesses.values(), key=lambda x: x.id):
        for w in h.wires:
            i = project.interfaces.get(w.interface_id or "")
            itype = project.interface_types.get(i.type_id) if i else None
            length = wire_length(h, w)
            if not (
                i and itype and i.max_current_a is not None and length and w.gauge_awg is not None
            ):
                continue
            if not 0 <= w.gauge_awg <= 40:  # a hand-edited gauge must not stop the whole check
                yield Hit(
                    w.id, f"Wire {w.id} has AWG {w.gauge_awg}, which is not a wire size (0 to 40)"
                )
                continue
            n = settings.drop_conductors(project, itype.category)
            drop = voltage_drop_v(i.max_current_a, rho, length, w.gauge_awg, n)
            if exceeds(drop, limit):
                yield Hit(w.id, f"Wire {w.id} drops {drop:.3g} V, more than the {limit:g} V limit")


def _spare_pins(project: Project) -> Iterator[Hit]:
    fraction = number(cfg(project, "derating").get("spare_pin_fraction"))
    if fraction is None:
        return
    for c in sorted(project.connectors.values(), key=lambda x: x.id):
        if not c.pins or not any(p.interface_id for p in c.pins):
            continue
        spare = sum(1 for p in c.pins if p.interface_id is None and not p.signal)
        if exceeds(fraction * len(c.pins), spare):
            yield Hit(
                c.id,
                f"{c.id} has {spare} spare pin(s) of {len(c.pins)}, fewer than the required {fraction:.0%}",
            )


# ---- shields ---------------------------------------------------------------------------------------


def _shield_unterminated(project: Project) -> Iterator[Hit]:
    g = cfg(project, "generation")
    if g.get("shield_end_a") is None and g.get("shield_end_b") is None:
        return  # no grounding concept yet: "not checked" is reported instead
    for h in sorted(project.harnesses.values(), key=lambda x: x.id):
        for s in h.shields:
            if s.kind == "twisted_pair":
                continue  # a twisted pair has no shield to terminate
            if s.end_a == "floating" and s.end_b == "floating":
                yield Hit(
                    f"{h.id}.{s.id}", f"Shield {s.id} in {h.id} is not connected at either end"
                )


def _shield_wrong_end(project: Project) -> Iterator[Hit]:
    g = cfg(project, "generation")
    want = (g.get("shield_end_a"), g.get("shield_end_b"))
    if None in want:
        return
    for h in sorted(project.harnesses.values(), key=lambda x: x.id):
        for s in h.shields:
            if s.kind in ("twisted_pair", "coax"):
                continue  # a twisted pair has no shield to ground; a coax is bonded at both ends
            if (s.end_a, s.end_b) != want:
                yield Hit(
                    f"{h.id}.{s.id}",
                    f"Shield {s.id} in {h.id} is {s.end_a}/{s.end_b} but the grounding concept says {want[0]}/{want[1]}",
                )


# ---- segregation -----------------------------------------------------------------------------------


def _carried(project: Project, h: Harness) -> list[InterfaceInstance]:
    return [
        project.interfaces[i]
        for i in sorted(_wire_interfaces(project, h))
        if i in project.interfaces
    ]


def _chains_mixed(project: Project) -> Iterator[Hit]:
    if not flag(cfg(project, "segregation"), "forbid_nominal_with_redundant"):
        return
    for h in sorted(project.harnesses.values(), key=lambda x: x.id):
        if {i.redundancy for i in _carried(project, h)} >= {"nominal", "redundant"}:
            yield Hit(h.id, f"{h.id} carries both nominal and redundant interfaces")
    for c in sorted(project.connectors.values(), key=lambda x: x.id):
        sides = {
            project.interfaces[p.interface_id].redundancy
            for p in c.pins
            if p.interface_id in project.interfaces
        }
        if {"nominal", "redundant"} <= sides:
            yield Hit(c.id, f"Connector {c.id} carries both nominal and redundant interfaces")


def _pyro_mixed(project: Project) -> Iterator[Hit]:
    if not flag(cfg(project, "segregation"), "forbid_pyro_with_other"):
        return

    def cats(ids: list[InterfaceInstance]) -> set[str]:
        return {
            project.interface_types[i.type_id].category
            for i in ids
            if i.type_id in project.interface_types
        }

    for h in sorted(project.harnesses.values(), key=lambda x: x.id):
        c = cats(_carried(project, h))
        if "pyro" in c and len(c) > 1:
            yield Hit(h.id, f"{h.id} mixes pyro (firing) lines with other interfaces")
    for conn in sorted(project.connectors.values(), key=lambda x: x.id):
        c = cats(
            [
                project.interfaces[p.interface_id]
                for p in conn.pins
                if p.interface_id in project.interfaces
            ]
        )
        if "pyro" in c and len(c) > 1:
            yield Hit(
                conn.id, f"Connector {conn.id} mixes pyro (firing) lines with other interfaces"
            )


def _category_pairs(project: Project) -> list[tuple[str, str]]:
    raw = cfg(project, "segregation").get("category_pairs_to_separate")
    pairs = (
        [tuple(p) for p in raw if isinstance(p, list) and len(p) == 2]
        if isinstance(raw, list)
        else []
    )
    return [(str(a), str(b)) for a, b in pairs]


def _category_mixed(project: Project) -> Iterator[Hit]:
    pairs = _category_pairs(project)
    for h in sorted(project.harnesses.values(), key=lambda x: x.id):
        cats = {
            project.interface_types[i.type_id].category
            for i in _carried(project, h)
            if i.type_id in project.interface_types
        }
        for a, b in pairs:
            if a in cats and b in cats:
                yield Hit(
                    f"{h.id}.{a}+{b}",
                    f"{h.id} mixes {a} and {b} interfaces, which the project keeps apart",
                )


def _emc_pairs(project: Project) -> list[tuple[str, str]]:
    raw = cfg(project, "emc").get("conflicting_class_pairs")
    pairs = (
        [tuple(p) for p in raw if isinstance(p, list) and len(p) == 2]
        if isinstance(raw, list)
        else []
    )
    return [(str(a), str(b)) for a, b in pairs]


def _emc_mixed(project: Project) -> Iterator[Hit]:
    pairs = _emc_pairs(project)
    for h in sorted(project.harnesses.values(), key=lambda x: x.id):
        classes = {
            project.interface_types[i.type_id].emc_class
            for i in _carried(project, h)
            if i.type_id in project.interface_types
        }
        for a, b in pairs:
            if a in classes and b in classes:
                yield Hit(f"{h.id}.{a}+{b}", f"{h.id} mixes EMC classes {a} and {b}")


def _config_invalid(project: Project) -> Iterator[Hit]:
    for issue in validate_config(project):
        yield Hit(issue.object_id or issue.code, issue.message)


def _released_modified(project: Project) -> Iterator[Hit]:
    for issue in release_integrity(project):
        yield Hit(issue.object_id or issue.code, issue.message)


# ---- what could not be checked ---------------------------------------------------------------------


def _carries_current(project: Project, w: Wire) -> bool:
    i = project.interfaces.get(w.interface_id or "")
    return i is not None and i.max_current_a is not None


def _current_gaps(project: Project, table: dict[int, float] | None) -> Iterator[Hit]:
    """Wires the current checks skipped for lack of a bundle factor or a gauge."""
    if table is None:
        return  # the placeholder note already says that no current limit was checked
    d = cfg(project, "derating")
    by_count = d.get("bundle_factor_by_count")
    if isinstance(by_count, dict) and by_count:
        short = [
            f"{h.id} ({len(h.wires)} wires)"
            for h in sorted(project.harnesses.values(), key=lambda x: x.id)
            if any(_carries_current(project, w) for w in h.wires)
            and bundle_k(by_count, len(h.wires)) is None
        ]
        if short:
            yield Hit(
                "bundle-factor",
                f"Wire and bundle current were not checked for {', '.join(short)}: the table of bundle factors has no entry for that many wires",
            )
    no_gauge = sorted(
        w.id
        for h in project.harnesses.values()
        for w in h.wires
        if w.gauge_awg is None and _carries_current(project, w)
    )
    if no_gauge:
        yield Hit(
            "wire-gauge",
            f"Wire current was not checked for {len(no_gauge)} wire(s) without a gauge (first: {no_gauge[0]})",
        )


def _voltage_drop_gaps(project: Project) -> Iterator[Hit]:
    """Wires the voltage-drop check skipped for lack of a gauge or a length."""
    limit = number(cfg(project, "derating").get("max_voltage_drop_v"))
    rho, _missing = settings.resistivity(project)
    if limit is None or rho is None:
        return  # the placeholder note already says that the check did not run
    no_gauge: list[str] = []
    no_length: list[str] = []
    for h in sorted(project.harnesses.values(), key=lambda x: x.id):
        for w in h.wires:
            i = project.interfaces.get(w.interface_id or "")
            if not (i and i.type_id in project.interface_types and i.max_current_a is not None):
                continue
            if w.gauge_awg is None:
                no_gauge.append(w.id)
            if wire_length(h, w) is None:
                no_length.append(w.id)
    if no_gauge or no_length:
        parts = []
        if no_gauge:
            parts.append(f"{len(no_gauge)} wire(s) without a gauge (first: {no_gauge[0]})")
        if no_length:
            parts.append(f"{len(no_length)} wire(s) without a length (first: {no_length[0]})")
        yield Hit("voltage-drop-wires", f"Voltage drop was not checked for {' and '.join(parts)}")


def _wires_without_interface(project: Project) -> Iterator[Hit]:
    """Wires that name no interface (drawn by hand, or made from a link) carry no current or
    voltage, so the checks that read an interface skip them. Say so, once for the project."""
    short = []
    for h in sorted(project.harnesses.values(), key=lambda x: x.id):
        n = sum(1 for w in h.wires if w.interface_id not in project.interfaces)
        if n:
            short.append(f"{n} wire(s) of harness {h.id}")
    if short:
        yield Hit(
            "wire-interface",
            f"Current, voltage-drop and bundle checks did not run for {', '.join(short)}: "
            "they have no interface to take a current from",
        )


def _nothing_to_evaluate(project: Project) -> Iterator[Hit]:
    """A rule that is ready to run but found nothing to look at must not read as a pass: no
    interface has a current or voltage, or no interface type has an EMC class. Each note is
    raised only when the rule's own values are set; until then the rule is pending anyway."""
    d = cfg(project, "derating")
    has_design = bool(project.interfaces) or any(h.wires for h in project.harnesses.values())
    if has_design and not any(i.max_current_a is not None for i in project.interfaces.values()):
        sentence = "No interface has a current yet, so the {} did not run"
        table = ampacity_table(d.get("ampacity_a_by_awg"))
        if number(d.get("contact_current_factor")) is not None:
            yield Hit("no-current-contact", sentence.format("contact current check"))
        if _derated_limit_ready(project):
            yield Hit("no-current-wire", sentence.format("wire current check"))
        if table is not None and _bundle_table_given(d):
            yield Hit("no-current-bundle", sentence.format("bundle current check"))
        if (
            number(d.get("max_voltage_drop_v")) is not None
            and settings.resistivity(project)[0] is not None
        ):
            yield Hit("no-current-drop", sentence.format("voltage drop check"))
    if has_design and not any(i.voltage_v is not None for i in project.interfaces.values()):
        sentence = "No interface has a voltage yet, so the {} did not run"
        if (
            number(d.get("connector_voltage_factor_withstand")) is not None
            or number(d.get("connector_voltage_factor_rated")) is not None
        ):
            yield Hit("no-voltage-connector", sentence.format("connector voltage check"))
        if number(d.get("wire_voltage_factor")) is not None:
            yield Hit("no-voltage-wire", sentence.format("wire voltage check"))
    if project.harnesses and not any(t.emc_class for t in project.interface_types.values()):
        sentence = "No interface type has an EMC class yet, so the {} did not run"
        if _emc_pairs(project):
            yield Hit("no-emc-class", sentence.format("EMC class check"))
        if cfg(project, "emc").get("same_class_one_bundle") is True:
            yield Hit("no-emc-class-split", sentence.format("one-bundle-per-class check"))


def _unchecked(project: Project) -> Iterator[Hit]:
    d, g = cfg(project, "derating"), cfg(project, "generation")
    has_current = any(i.max_current_a is not None for i in project.interfaces.values())
    if has_current and (
        number(d.get("contact_current_factor")) is None or not _derated_limit_ready(project)
    ):
        yield Hit(
            "derating",
            "Current and derating limits were not checked: the derating values are still placeholders",
        )
    table = ampacity_table(d.get("ampacity_a_by_awg"))
    if table is not None:
        missing_gauges = sorted(
            {
                w.gauge_awg
                for h in project.harnesses.values()
                for w in h.wires
                if w.gauge_awg is not None
                and w.gauge_awg not in table
                and (i := project.interfaces.get(w.interface_id or "")) is not None
                and i.max_current_a is not None
            }
        )
        if missing_gauges:
            yield Hit(
                "derating-gauge",
                f"Wire current was not checked for AWG {', '.join(str(g) for g in missing_gauges)}: the ampacity table has no value for it",
            )
    yield from _current_gaps(project, table)
    if number(d.get("contact_current_factor")) is not None:
        unrated = sorted(
            {
                box.part_id
                for i in project.interfaces.values()
                if i.max_current_a is not None
                for e in i.endpoints
                if (box := project.connectors.get(e.connector_id or "")) is not None
                and contact_rating(project, box) is None
            }
        )
        if unrated:
            yield Hit(
                "contact-rating",
                f"Contact current was not checked for {', '.join(unrated)}: the part has no contact rating",
            )
    if has_current and (
        number(d.get("max_voltage_drop_v")) is None or settings.resistivity(project)[0] is None
    ):
        yield Hit(
            "voltage-drop",
            "Voltage drop was not checked: the limit or the conductor resistivity is still a placeholder",
        )
    yield from _voltage_drop_gaps(project)
    if any(h.shields for h in project.harnesses.values()) and None in (
        g.get("shield_end_a"),
        g.get("shield_end_b"),
    ):
        yield Hit(
            "grounding",
            "Shield grounding was not checked against a concept: it is still a placeholder",
        )
    if project.interfaces and not _category_pairs(project):
        yield Hit(
            "separation",
            "Power, signal and sensitive-analog separation was not checked: the category pairs are still a placeholder",
        )
    if project.harnesses and not _emc_pairs(project):
        yield Hit(
            "emc", "EMC class separation was not checked: the EMC rules are still a placeholder"
        )
    if (
        any(c.pins for c in project.connectors.values())
        and number(d.get("spare_pin_fraction")) is None
    ):
        yield Hit(
            "spare-pins",
            "Spare pins were not checked: the required fraction is still a placeholder",
        )
    yield from _wires_without_interface(project)
    yield from _nothing_to_evaluate(project)
    yield from standard_unchecked(project)
    yield from electrical_unchecked(project)


# ---- core/drc/standard_rules.py of 4.4.0 ----------------------------------------------------------


def _bundle_table_set(project: Project) -> bool:
    return isinstance(cfg(project, "derating").get("bundle_factor_by_count"), dict)


def bundle_factor(project: Project, count: int) -> float | None:
    """K from Table 6-41 for a bundle of `count` wires (see `sizing.bundle_k`)."""
    return bundle_k(cfg(project, "derating").get("bundle_factor_by_count"), count)


def bundle_wire_count(h: Harness) -> int:
    return len(h.wires)


def _bundle_current(project: Project) -> Iterator[Hit]:
    """IBW = ISW x K (30-11C 6.32.5.1). ISW is the ampacity table of the project; the bundle is
    every wire of the harness (conservative; L of Table 6-42 is not applied). The limit is the one
    of `current-over-wire` (`sizing.wire_current_limit`, which also takes the temperature factor);
    an unset temperature factor counts as 1 here, so the bundle check still runs without it."""
    derating = cfg(project, "derating")
    table = ampacity_table(derating.get("ampacity_a_by_awg"))
    if table is None or not _bundle_table_set(project):
        return
    for h in sorted(project.harnesses.values(), key=lambda x: x.id):
        temp = number(derating.get("temperature_derating"))
        for w in h.wires:
            n = bundle_size(project, h, w)
            k = bundle_factor(project, n)
            if k is None:
                continue
            i = project.interfaces.get(w.interface_id or "")
            if i is None or i.max_current_a is None or w.gauge_awg not in table:
                continue
            limit = wire_current_limit(derating, w.gauge_awg, n, temperature_optional=True)
            if limit is not None and exceeds(i.max_current_a, limit):
                factors = f"K {k:g}" + (
                    f" x temperature factor {temp:g}" if temp is not None else ""
                )
                where = (
                    f"a bundle of {n} wires ({h.id})"
                    if basis(project) == "all_wires"
                    else f"a bundle of {n} wires ({BASIS_TEXT[basis(project)]}, {h.id})"
                )
                yield Hit(
                    w.id,
                    f"Wire {w.id} (AWG {w.gauge_awg}) carries {i.max_current_a:g} A but {where} allows {limit:g} A (single wire {table[w.gauge_awg]:g} A x {factors})",
                )
