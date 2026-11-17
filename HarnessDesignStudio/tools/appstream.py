# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Write and check the AppStream metainfo file of the Linux packages (the App Center page).

Usage: python -m tools.appstream write FILE
       python -m tools.appstream check FILE
`write` fills the template `packaging/appstream/metainfo.xml.in` with a `<releases>` block made from
the newest full releases of `CHANGELOG.md` (version and date of each `## X.Y.Z (YYYY-MM-DD; ...)`
heading) and the first two sentences of `docs/releases/X.Y.Z.md` (else of the changelog section),
so nobody edits XML at a release. A release's date is the date of its tag `vX.Y.Z` when the
repository has it (the day it was published: the tag workflow makes the tag at publication), else
the date of its changelog heading (the day it was prepared); the release workflow checks out with
all tags, a shallow checkout has none. The output depends on the files only (no clock, no build time).
`check` reads a finished file and fails unless it is well-formed and has what the packages need
(the component ID, the licences, the launchable, the screenshots, a newest release that is the
program's version); when `appstreamcli` is installed it also runs `appstreamcli validate --no-net`.
`tools/build_installer.py` writes the file into the tarball and `tools/build_deb.py` into the .deb.
"""

import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET  # noqa: S405 (reads our own template and our own output)
from pathlib import Path
from typing import NamedTuple
from xml.sax.saxutils import escape, quoteattr  # noqa: S406 (escaping only, no parsing)

from harness_design_studio import __version__

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "packaging" / "appstream" / "metainfo.xml.in"
DESKTOP_IN = ROOT / "packaging" / "ubuntu" / "harness-design-studio.desktop.in"
# Reverse-DNS from the GitHub owner 0h3xn4: a part may not start with a digit, so it gets "_"
# (as Flatpak and D-Bus names do); lower case, as appstreamcli's pedantic check asks.
COMPONENT_ID = "io.github._0h3xn4.harness_design_studio"
FILE_NAME = f"{COMPONENT_ID}.metainfo.xml"
DESKTOP_ID = "harness-design-studio.desktop"  # the name of the desktop file stays
REPO_URL = "https://github.com/0h3xn4/wireviz_harness-design-studio"
SCREENSHOT_URL = (
    "https://raw.githubusercontent.com/0h3xn4/wireviz_harness-design-studio/master/"
    "HarnessDesignStudio/docs/img/"
)
BINARIES = ("harness-design-studio-gui", "harness-design-studio", "harness")
PROJECT_LICENSE = "GPL-3.0-only"
METADATA_LICENSES = ("FSFAP", "CC0-1.0")
RELEASES_SHOWN = 5
PLACEHOLDER = "  <!-- @RELEASES@ -->"
HEADING = re.compile(r"^## (\d+\.\d+\.\d+(?:rc\d+)?) \((\d{4}-\d{2}-\d{2})[;)]", re.M)


class Release(NamedTuple):
    version: str
    date: str
    text: str  # one or two plain sentences


def plain(markdown: str) -> str:
    """Markdown inline text as plain text: links keep their words, marks and code ticks go."""
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", markdown)
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"\1", text)
    return " ".join(text.split())


def first_sentences(markdown: str, count: int = 2) -> str:
    """The first `count` sentences of the first paragraph, as plain text."""
    paragraph = plain(markdown.strip().split("\n\n", 1)[0])
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(])", paragraph)
    return " ".join(sentences[:count])


def tag_dates(root: Path = ROOT) -> dict[str, str]:
    """The date of each tag `vX.Y.Z` of the repository that holds `root` (version -> YYYY-MM-DD), or
    nothing when git or the tags are not there. The date of an annotated tag is the day the tag
    workflow made it, which is the day the release was published."""
    git = shutil.which("git")
    if git is None:
        return {}
    try:
        run = subprocess.run(  # noqa: S603 (a fixed tool, no input from outside)
            [
                git,
                "-C",
                str(root),
                "for-each-ref",
                "refs/tags",
                "--format=%(refname:short) %(creatordate:short)",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except OSError, subprocess.SubprocessError:
        return {}
    if run.returncode != 0:
        return {}
    dates: dict[str, str] = {}
    for line in run.stdout.splitlines():
        name, _, date = line.partition(" ")
        if re.fullmatch(r"v\d+\.\d+\.\d+(?:rc\d+)?", name) and re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", date
        ):
            dates[name[1:]] = date
    return dates


def releases(
    root: Path = ROOT,
    version: str = __version__,
    shown: int = RELEASES_SHOWN,
    dates: dict[str, str] | None = None,
) -> list[Release]:
    """The newest `shown` releases of CHANGELOG.md, newest first. Release candidates are left out,
    unless the program itself is one. `dates` (version -> date, by default the tag dates) replaces
    the date of a changelog heading."""
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    published = tag_dates(root) if dates is None else dates
    found: list[Release] = []
    for match in HEADING.finditer(changelog):
        number, date = match.groups()
        if "rc" in number and number != version:
            continue
        notes = root / "docs" / "releases" / f"{number}.md"
        if notes.is_file():
            text = first_sentences(notes.read_text(encoding="utf-8"))
        else:
            body = changelog[match.end() :].split("\n## ", 1)[0].split("\n", 1)[-1]
            text = first_sentences(body)
        found.append(Release(number, published.get(number, date), text))
        if len(found) == shown:
            break
    return found


def releases_xml(items: list[Release]) -> str:
    lines = ["  <releases>"]
    for r in items:
        kind = "development" if "rc" in r.version else "stable"
        lines += [
            f"    <release version={quoteattr(r.version)} date={quoteattr(r.date)} type={quoteattr(kind)}>",
            "      <description>",
            f"        <p>{escape(r.text)}</p>",
            "      </description>",
            f'      <url type="details">{escape(f"{REPO_URL}/releases/tag/v{r.version}")}</url>',
            "    </release>",
        ]
    lines.append("  </releases>")
    return "\n".join(lines)


def render(root: Path = ROOT, version: str = __version__) -> str:
    """The finished metainfo file. Fails when CHANGELOG.md has no heading for `version`."""
    items = releases(root, version)
    if not items or items[0].version != version:
        raise SystemExit(
            f"error: CHANGELOG.md has no '## {version} (YYYY-MM-DD; ...)' heading above the other "
            "releases, so the App Center data cannot name this version"
        )
    template = (root / TEMPLATE.relative_to(ROOT)).read_text(encoding="utf-8")
    if template.count(PLACEHOLDER + "\n") != 1:
        raise SystemExit(f"error: {TEMPLATE.name} must hold the line '{PLACEHOLDER}' once")
    return template.replace(PLACEHOLDER, releases_xml(items))


def write(target: Path, root: Path = ROOT, version: str = __version__) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(root, version), encoding="utf-8", newline="\n")
    return target


def desktop_categories(text: str) -> list[str]:
    line = next((ln for ln in text.splitlines() if ln.startswith("Categories=")), "Categories=")
    return [c for c in line.split("=", 1)[1].split(";") if c]


def problems(text: str, version: str = __version__) -> list[str]:
    """What is wrong with a finished metainfo file (empty when nothing is)."""
    try:
        comp = ET.fromstring(text)  # noqa: S314 (the file this module wrote)
    except ET.ParseError as exc:
        return [f"not well-formed XML: {exc}"]
    found: list[str] = []

    def one(path: str) -> str:
        el = comp.find(path)
        if el is None or not (el.text or "").strip():
            found.append(f"no <{path}>")
            return ""
        return (el.text or "").strip()

    if comp.tag != "component" or comp.get("type") != "desktop-application":
        found.append('the root is not <component type="desktop-application">')
    if one("id") != COMPONENT_ID:
        found.append(f"the component ID is not {COMPONENT_ID}")
    one("name")
    one("summary")
    if one("metadata_license") not in METADATA_LICENSES:
        found.append(f"metadata_license is not one of {', '.join(METADATA_LICENSES)}")
    if one("project_license") != PROJECT_LICENSE:
        found.append(f"project_license is not {PROJECT_LICENSE}")
    if not comp.findall("description/p"):
        found.append("no <description> with a paragraph")
    one("developer/name")
    if one("launchable[@type='desktop-id']") != DESKTOP_ID:
        found.append(f"the launchable is not {DESKTOP_ID}")
    if one("url[@type='homepage']") != REPO_URL:
        found.append(f"the homepage is not {REPO_URL}")
    rating = comp.find("content_rating")
    if rating is None or rating.get("type") != "oars-1.1":
        found.append('no <content_rating type="oars-1.1">')
    if [b.text for b in comp.findall("provides/binary")] != list(BINARIES):
        found.append(f"<provides> does not list the binaries {', '.join(BINARIES)}")
    cats = [c.text for c in comp.findall("categories/category")]
    if DESKTOP_IN.is_file() and cats != desktop_categories(DESKTOP_IN.read_text(encoding="utf-8")):
        found.append("the categories differ from those of the desktop file")
    shots = comp.findall("screenshots/screenshot")
    if not 3 <= len(shots) <= 5:
        found.append(f"{len(shots)} screenshots, want 3 to 5")
    if [s.get("type") for s in shots].count("default") != 1:
        found.append("not exactly one default screenshot")
    for shot in shots:
        image = shot.find("image")
        url = (image.text or "") if image is not None else ""
        if not url.startswith(SCREENSHOT_URL) or not url.endswith(".png"):
            found.append(f"a screenshot is not a picture of docs/img/: {url!r}")
        if not (shot.findtext("caption") or "").strip():
            found.append(f"a screenshot has no caption: {url!r}")
    rels = comp.findall("releases/release")
    if not rels:
        found.append("no <release>")
    elif rels[0].get("version") != version:
        found.append(f"the newest release is {rels[0].get('version')}, the program is {version}")
    for rel in rels:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", rel.get("date", "")):
            found.append(f"release {rel.get('version')} has no date YYYY-MM-DD")
    dates = [rel.get("date", "") for rel in rels]
    if dates != sorted(dates, reverse=True):
        found.append("the releases are not newest first")
    return found


def appstreamcli(path: Path) -> tuple[int, str] | None:
    """`appstreamcli validate --no-net` of the file (exit code, output), or None without the tool."""
    tool = shutil.which("appstreamcli")
    if tool is None:
        return None
    run = subprocess.run(  # noqa: S603 (a fixed tool on a file we wrote)
        [tool, "validate", "--no-net", "--no-color", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    return run.returncode, (run.stdout + run.stderr).strip()


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in ("write", "check"):
        print(__doc__, file=sys.stderr)
        return 2
    path = Path(argv[1])
    if argv[0] == "write":
        print(write(path))
        return 0
    bad = problems(path.read_text(encoding="utf-8"))
    for p in bad:
        print(f"error: {path.name}: {p}", file=sys.stderr)
    tool = appstreamcli(path)
    if tool is None:
        print("appstreamcli is not installed: its validation was skipped")
    else:
        print(tool[1])
        if tool[0] != 0:
            bad.append("appstreamcli")
    if not bad:
        print(f"{path.name}: ok")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
