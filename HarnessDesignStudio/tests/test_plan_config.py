# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""D-242, design of 3.0.0 sections 4.1, 6 and 10: the headless part of the editor of the harness
plan (pull request 7), tested without Qt. `core/plan_config.py` (the settings of
`config/harness_plan.json` as the Settings page changes them, the example colour code taken on
purpose, the paste of two columns), `build_data.plan_set_part_link`, `document.shown_when_empty`
and `library_folder.describe_parts`. Example data only."""

import pytest

from harness_design_studio.core import document, library_folder, plan_config
from harness_design_studio.core.build_data import plan_set_part_link
from harness_design_studio.core.commands import DeleteConfig, History, SetConfig
from harness_design_studio.core.configcheck import validate_harness_plan
from harness_design_studio.core.edit import EditError
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.model import Project
from harness_design_studio.core.samples import mini3

LINK = "https://example.org/datasheet.pdf"


def project() -> Project:
    p = mini3()
    generate_project(p)
    return p


def part_of(p: Project) -> str:
    return p.harnesses["W001"].connectors[0].part_id


def test_no_file_reads_as_the_defaults() -> None:
    assert plan_config.plan_values(mini3()) == {
        "colour_rule": "wire",
        "colour_codes": [],
        "notes": [],
    }


def test_the_first_value_makes_the_file_and_the_defaults_remove_it() -> None:
    p = project()
    h = History(p)
    ops = plan_config.plan_settings_edit(p, colour_rule="pin_code")
    assert [type(o) for o in ops] == [SetConfig]
    h.execute("rule", ops)
    assert p.config["harness_plan"].values == {"colour_rule": "pin_code"}
    assert plan_config.plan_settings_edit(p, colour_rule="pin_code") == []  # nothing to do
    ops = plan_config.plan_settings_edit(p, colour_rule="wire")
    assert ops == [DeleteConfig("harness_plan")]
    h.execute("back", ops)
    assert "harness_plan" not in p.config
    h.undo()
    assert p.config["harness_plan"].values["colour_rule"] == "pin_code"
    assert plan_config.plan_settings_edit(mini3(), colour_rule="wire") == []


def test_what_validate_refuses_is_refused_with_its_words() -> None:
    p = project()
    part = part_of(p)
    two = [{"name": "a", "parts": [part], "pins": {}}, {"name": "b", "parts": [part], "pins": {}}]
    with pytest.raises(EditError, match="more than one code"):
        plan_config.plan_settings_edit(p, colour_codes=two)
    with pytest.raises(EditError, match="more than once"):
        plan_config.plan_settings_edit(
            p, colour_codes=[{"name": "a", "pins": {}}, {"name": "a", "pins": {}}]
        )
    with pytest.raises(EditError, match="needs a name"):
        plan_config.plan_settings_edit(p, colour_codes=[{"name": " "}])
    with pytest.raises(EditError, match="colour rule"):
        plan_config.plan_settings_edit(p, colour_rule="rainbow")
    with pytest.raises(EditError, match="note lines"):
        plan_config.plan_settings_edit(p, notes=[f"line {n}" for n in range(21)])


def test_the_example_code_is_taken_only_on_purpose_and_stays_marked() -> None:
    p = project()
    part = part_of(p)
    assert "harness_plan" not in p.config  # never applied by itself
    History(p).execute("example", plan_config.plan_example_code(p, [part, part]))
    values = p.config["harness_plan"].values
    assert values["colour_rule"] == "pin_code"
    (code,) = values["colour_codes"]
    assert code["name"] == "example" and code["example"] is True and code["parts"] == [part]
    assert list(code["pins"]) == [str(n) for n in range(1, 38)]
    assert validate_harness_plan(p) == []
    with pytest.raises(EditError, match="already"):
        plan_config.plan_example_code(p, [part])
    with pytest.raises(EditError, match="connector parts"):
        plan_config.plan_example_code(mini3(), [])
    with pytest.raises(EditError, match="not in the library"):
        plan_config.plan_example_code(mini3(), ["NO-SUCH-PART"])


def test_the_mark_is_written_only_while_it_is_on() -> None:
    p = project()
    History(p).execute("x", plan_config.plan_example_code(p, [part_of(p)]))
    code = dict(plan_config.plan_values(p)["colour_codes"][0], example=False)
    History(p).execute("off", plan_config.plan_settings_edit(p, colour_codes=[code]))
    assert "example" not in p.config["harness_plan"].values["colour_codes"][0]


def test_a_read_only_project_is_refused() -> None:
    p = mini3()
    p.read_only = True
    with pytest.raises(EditError, match="read-only"):
        plan_config.plan_settings_edit(p, colour_rule="pin_code")


def test_the_paste_reads_tabs_commas_and_semicolons_with_or_without_a_heading() -> None:
    assert plan_config.parse_colour_table("Pin,Colour\n1,Black\n2,Brown\n") == {
        "1": "Black",
        "2": "Brown",
    }
    assert plan_config.parse_colour_table("Pin\tColor\r\n01\tWh / Bl\r\n") == {"01": "Wh / Bl"}
    assert plan_config.parse_colour_table("01;Wh / Bl\n") == {"01": "Wh / Bl"}
    assert plan_config.parse_colour_table("1\tBlack\t\n\n") == {"1": "Black"}
    assert plan_config.parse_colour_table("1,Black\n1,Black\n") == {"1": "Black"}
    for bad, words in (("", "nothing"), ("1\n", "Row 1"), ("1,Black\n1,Brown\n", "two colours")):
        with pytest.raises(EditError, match=words):
            plan_config.parse_colour_table(bad)


def test_the_link_of_a_part_is_a_web_link_or_nothing() -> None:
    p = project()
    part = part_of(p)
    h = History(p)
    h.execute("link", plan_set_part_link(p, part, f"  {LINK} "))
    assert p.parts[part].link == LINK
    assert plan_set_part_link(p, part, LINK) == []
    for bad in ("file:///srv/share/a.pdf", "javascript:alert(1)", "\\\\share\\a.pdf"):
        with pytest.raises(EditError, match="https://"):
            plan_set_part_link(p, part, bad)
    with pytest.raises(EditError, match="does not exist"):
        plan_set_part_link(p, "NO-SUCH-PART", LINK)
    h.execute("clear", plan_set_part_link(p, part, ""))
    assert p.parts[part].link is None


def test_what_the_cover_shows_for_an_empty_field() -> None:
    p = project()
    assert document.shown_when_empty(p) == {
        "system": p.meta.name,
        "title": f"{p.meta.name} Harness Plan",
    }
    assert document.shown_when_empty(p, "W001") == {
        "title": f"{p.meta.name} Harness Plan",
        "version": p.harnesses["W001"].version,
    }


def test_the_parts_of_a_device_file_with_their_links() -> None:
    data = {
        "devices": [
            {
                "unit": {"id": "DEV1"},
                "connectors": [{"part_id": "P-1", "pins": [{"id": "1", "contact_part": "C-1"}]}],
            },
            {"unit": {"id": "DEV2"}, "connectors": [{"part_id": "P-2", "pins": []}]},
        ],
        "parts": [
            {"id": "C-1", "link": "file:///srv/share"},
            {"id": "P-1", "description": "Example connector", "link": LINK},
            {"id": "P-2", "link": LINK},
            "not a record",
        ],
    }
    assert library_folder.describe_parts(data, "DEV1") == [
        {"part": "C-1", "description": "", "link": ""},  # a link that is not a web link: none
        {"part": "P-1", "description": "Example connector", "link": LINK},
    ]
    assert library_folder.describe_parts({}, "DEV1") == []
