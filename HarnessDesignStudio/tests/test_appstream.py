# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The App Center page of the Linux packages: the AppStream metainfo file (tools/appstream.py).

The owner's App Center showed the 2.1.1 .deb with no screenshots, no release details, an unknown
licence and no age rating (2026-11-17): the package had no metainfo file.
"""

import re
import shutil
import struct
import subprocess
import xml.etree.ElementTree as ET  # noqa: S405
from pathlib import Path

import pytest

from harness_design_studio import __version__
from tools import appstream

ROOT = Path(__file__).resolve().parents[1]
PK = ROOT / "packaging" / "ubuntu"


@pytest.fixture(scope="module")
def text() -> str:
    return appstream.render()


def test_the_generated_file_is_well_formed_and_complete(text: str) -> None:
    comp = ET.fromstring(text)  # noqa: S314
    assert comp.tag == "component" and comp.get("type") == "desktop-application"
    assert comp.findtext("id") == appstream.COMPONENT_ID
    assert f"{comp.findtext('id')}.metainfo.xml" == appstream.FILE_NAME
    for tag in ("name", "summary", "metadata_license", "developer/name"):
        assert (comp.findtext(tag) or "").strip(), tag
    assert comp.findtext("project_license") == "GPL-3.0-only"
    assert comp.findtext("metadata_license") in ("FSFAP", "CC0-1.0")
    assert comp.findtext("launchable[@type='desktop-id']") == "harness-design-studio.desktop"
    assert comp.findtext("url[@type='homepage']") == appstream.REPO_URL
    assert comp.findtext("url[@type='bugtracker']") == f"{appstream.REPO_URL}/issues"
    rating = comp.find("content_rating")
    assert rating is not None and rating.get("type") == "oars-1.1" and len(rating) == 0
    assert [b.text for b in comp.findall("provides/binary")] == [
        "harness-design-studio-gui",
        "harness-design-studio",
        "harness",
    ]
    assert appstream.problems(text) == []


def test_the_developer_is_not_a_personal_name(text: str) -> None:
    """The legal texts name the owner by the GitHub handle (compliance/legal/texts.md)."""
    comp = ET.fromstring(text)  # noqa: S314
    assert comp.findtext("developer/name") == "0h3xn4"
    assert "SPDX-FileCopyrightText: 2026 0h3xn4" in (
        ROOT / "compliance" / "legal" / "texts.md"
    ).read_text(encoding="utf-8")


def test_the_newest_release_is_the_program_version(text: str) -> None:
    rels = ET.fromstring(text).findall("releases/release")  # noqa: S314
    assert rels[0].get("version") == __version__
    assert 1 <= len(rels) <= appstream.RELEASES_SHOWN
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    for rel in rels:
        version, date = rel.get("version"), rel.get("date")
        assert f"## {version} ({date}" in changelog, version  # the changelog's own date
        assert "rc" not in str(version) or version == __version__
        assert (rel.findtext("description/p") or "").startswith(("This is", "Version")), version
        assert rel.findtext("url[@type='details']") == (
            f"{appstream.REPO_URL}/releases/tag/v{version}"
        )


def test_the_releases_come_from_the_changelog_and_the_release_notes(tmp_path: Path) -> None:
    """A new `## X.Y.Z (date; ...)` heading is all a release needs; nobody edits the XML."""
    (tmp_path / "docs" / "releases").mkdir(parents=True)
    (tmp_path / "packaging" / "appstream").mkdir(parents=True)
    shutil.copy(appstream.TEMPLATE, tmp_path / "packaging" / "appstream" / "metainfo.xml.in")
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## Unreleased\n\n"
        "## 9.1.0 (2030-01-02; not a statement of compliance)\n\nVersion 9.1.0 adds *one* thing. "
        "It has a [link](docs/x.md) and `code`. A third sentence.\n\n"
        "## 9.1.0rc1 (2030-01-01; release candidate)\n\nA candidate.\n\n"
        "## 9.0.0 (2029-12-31; not a statement of compliance)\n\nOld.\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "releases" / "9.0.0.md").write_text(
        "This is **version 9.0.0**, a major release. It brings `X` & <Y>. Not this one.\n\n### More\n",
        encoding="utf-8",
    )
    out = appstream.render(tmp_path, "9.1.0")
    rels = ET.fromstring(out).findall("releases/release")  # noqa: S314
    assert [(r.get("version"), r.get("date"), r.get("type")) for r in rels] == [
        ("9.1.0", "2030-01-02", "stable"),
        ("9.0.0", "2029-12-31", "stable"),
    ]
    assert rels[0].findtext("description/p") == (
        "Version 9.1.0 adds one thing. It has a link and code."
    )
    assert rels[1].findtext("description/p") == (
        "This is version 9.0.0, a major release. It brings X & <Y>."
    )
    assert appstream.render(tmp_path, "9.1.0") == out  # deterministic: no clock, no build time
    # a release candidate that is the program itself is listed, as a development release
    log = tmp_path / "CHANGELOG.md"
    log.write_text(re.sub(r"## 9\.1\.0 \(.*?(?=## 9\.1\.0rc1)", "", log.read_text(), flags=re.S))
    rc = ET.fromstring(appstream.render(tmp_path, "9.1.0rc1")).findall("releases/release")  # noqa: S314
    assert [(r.get("version"), r.get("type")) for r in rc] == [
        ("9.1.0rc1", "development"),
        ("9.0.0", "stable"),
    ]
    with pytest.raises(SystemExit, match="no '## 9.2.0"):
        appstream.render(tmp_path, "9.2.0")  # a version without a changelog section


def test_the_output_does_not_depend_on_the_time(text: str) -> None:
    assert appstream.render() == text
    dates = set(re.findall(r"\d{4}-\d{2}-\d{2}", text))
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert all(f"({d}" in changelog for d in dates)


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def test_the_screenshots_are_pictures_of_the_repository(text: str) -> None:
    """App Center loads them from the web (raw.githubusercontent.com, branch master): each must be a
    picture of docs/img/ with the size the file says, small enough to load."""
    shots = ET.fromstring(text).findall("screenshots/screenshot")  # noqa: S314
    assert 3 <= len(shots) <= 5
    assert [s.get("type") for s in shots].count("default") == 1
    for shot in shots:
        image = shot.find("image")
        assert image is not None and image.get("type") == "source"
        url = image.text or ""
        assert url.startswith(appstream.SCREENSHOT_URL)
        picture = ROOT / "docs" / "img" / url.removeprefix(appstream.SCREENSHOT_URL)
        assert picture.is_file(), url
        assert 10_000 < picture.stat().st_size < 1_000_000, picture.name
        width, height = _png_size(picture)
        assert (image.get("width"), image.get("height")) == (str(width), str(height)), picture.name
        assert width >= 620 and height >= 350, picture.name  # readable in a software centre
        assert (shot.findtext("caption") or "").strip(), picture.name


def test_the_categories_are_those_of_the_desktop_file(text: str) -> None:
    comp = ET.fromstring(text)  # noqa: S314
    desktop = (PK / "harness-design-studio.desktop.in").read_text(encoding="utf-8")
    assert [c.text for c in comp.findall("categories/category")] == (
        appstream.desktop_categories(desktop)
    )


def test_the_check_finds_what_it_should(text: str) -> None:
    assert appstream.problems("<component") == [appstream.problems("<component")[0]]
    assert "not well-formed" in appstream.problems("<component")[0]
    wrong = text.replace("GPL-3.0-only", "GPL-3.0-or-later")
    assert any("project_license" in p for p in appstream.problems(wrong))
    old = text.replace(f'version="{__version__}"', 'version="0.0.1"', 1)
    assert any("newest release" in p for p in appstream.problems(old))
    assert any("ID" in p for p in appstream.problems(text.replace(appstream.COMPONENT_ID, "x.y")))


def test_check_on_the_command_line(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / appstream.FILE_NAME
    assert appstream.main(["write", str(target)]) == 0
    assert appstream.main(["check", str(target)]) == 0
    assert f"{appstream.FILE_NAME}: ok" in capsys.readouterr().out
    target.write_text(target.read_text().replace("oars-1.1", "oars-1.0"))
    assert appstream.main(["check", str(target)]) == 1
    assert appstream.main(["bogus"]) == 2


@pytest.mark.skipif(shutil.which("appstreamcli") is None, reason="appstreamcli not installed")
def test_appstreamcli_validates_the_file(tmp_path: Path) -> None:
    target = appstream.write(tmp_path / appstream.FILE_NAME)
    run = subprocess.run(
        ["appstreamcli", "validate", "--no-net", "--pedantic", "--no-color", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    # nothing to report at all, not even a pedantic hint
    assert "Validation was successful." in run.stdout and ":" not in run.stdout.split("\n")[0]


@pytest.mark.skipif(
    shutil.which("desktop-file-validate") is None, reason="desktop-file-validate not installed"
)
def test_desktop_file_validate_accepts_the_desktop_entries(tmp_path: Path) -> None:
    """The entry of the .deb and the one install.sh writes (with a quoted path)."""
    template = (PK / "harness-design-studio.desktop.in").read_text(encoding="utf-8")
    for exec_value in (
        "/usr/bin/harness-design-studio-gui",
        '"/home/a b/opt/harness-design-studio-gui"',
    ):
        entry = tmp_path / "harness-design-studio.desktop"
        entry.write_text(
            template.replace("@EXEC@", exec_value).replace("@ICON@", "harness-design-studio"),
            encoding="utf-8",
        )
        run = subprocess.run(
            ["desktop-file-validate", str(entry)], capture_output=True, text=True, check=False
        )
        assert run.returncode == 0 and not run.stdout.strip(), run.stdout + run.stderr
