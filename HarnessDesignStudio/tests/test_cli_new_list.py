# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""`new --list` in groups (design of 5.1.0 section 6, REQ-EX-01): a heading per group, the names in a column
as wide as the longest name plus two, `group` in `--json`, and a help of `new` that names no
example (the list is the one place that does)."""

import argparse
import json

import pytest

from harness_design_studio.cli.main import build_parser, main
from harness_design_studio.cli.start import GROUP_HEADINGS
from harness_design_studio.core import templates


def test_the_list_has_a_heading_per_group_and_one_column(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["new", "--list"]) == 0
    lines = capsys.readouterr().out.splitlines()
    width = max(len(t.name) for t in templates.TEMPLATES) + 2
    want: list[str] = []
    for group in templates.GROUPS:
        want.append(GROUP_HEADINGS[group])
        want += [t.name.ljust(width) + t.summary for t in templates.in_group(group)]
    assert lines == want
    assert lines[0] == "Start:" and lines[1].startswith("blank ") and lines[2].startswith("first-steps ")  # fmt: skip
    assert lines.index(GROUP_HEADINGS[templates.FEATURE]) == 1 + len(templates.in_group(templates.START))  # fmt: skip
    # the summaries start in one column, whatever the length of the name
    rows = [ln for ln in lines if ln not in GROUP_HEADINGS.values()]
    names = {t.name for t in templates.TEMPLATES}
    assert all(ln[:width].rstrip() in names and ln[width] != " " for ln in rows), rows


def test_the_groups_are_start_then_the_feature_examples() -> None:
    assert templates.GROUPS == ("start", "feature")
    assert [t.group for t in templates.TEMPLATES] == sorted(
        (t.group for t in templates.TEMPLATES), key=templates.GROUPS.index
    )  # Start first, in one run
    starts = [t.name for t in templates.in_group(templates.START)]
    assert starts == ["blank", "first-steps", "minimal-satellite", "small-satellite", "flatsat"]
    assert "full-connectors" in [t.name for t in templates.in_group(templates.FEATURE)]
    for t in templates.TEMPLATES:  # plain names: lowercase words joined by hyphens (T3)
        assert t.name == t.name.lower() and t.name.replace("-", "").isalpha(), t.name


def test_the_json_list_gives_the_group(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["new", "--list", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert [(t["name"], t["group"]) for t in doc["templates"]] == [
        (t.name, t.group) for t in templates.TEMPLATES
    ]
    assert all(set(t) == {"name", "title", "summary", "group"} for t in doc["templates"])


def test_the_help_of_new_names_no_example() -> None:
    parser = build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    line = next(c.help for c in sub._choices_actions if c.dest == "new")
    assert line == "create a new project from an example (`new --list` shows them)"
    for t in templates.TEMPLATES:
        assert t.name not in (line or ""), line
