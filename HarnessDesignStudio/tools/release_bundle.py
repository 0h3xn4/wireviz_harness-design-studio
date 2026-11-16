# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The release bundle: one archive on the release page for everything but the packages (D-232).

    python -m tools.release_bundle build DIST --version VERSION [--out FILE]
    python -m tools.release_bundle check FILE --version VERSION

From 2.0.1 on the release page carries the four packages, `SHA256SUMS`, its signature
`SHA256SUMS.sigstore.json` and one plain tar archive, `harness-design-studio-<version>-release-bundle.tar`,
that holds the rest (D-232 amends D-213). `build` takes these files from the folder DIST that the
release workflow fills:

- `DIST/sources/`: `SOURCES.txt` and the source files it lists (tools/fetch_sources.py) -> `sources/`
- `DIST/legal/sbom-*.cdx.json` -> `sbom/`
- `DIST/legal/third-party-inventory-*` -> `inventory/`
- `DIST/legal/THIRD_PARTY_NOTICES-*.txt` -> `notices/`
- `DIST/offline-audit-<version>.md` and `.json` -> `offline-audit/`
- `DIST/*.sigstore.json` (the signatures of the packages and of the SBOMs) -> `signatures/`

and a `README.txt`, all under one top folder named like the archive without `.tar`. The archive is
reproducible: entries sorted by name, one fixed time (`SOURCE_DATE_EPOCH`, else the time of the
last commit), owner and group 0, fixed modes and the GNU tar format (no pax headers, so no access
or change times). It is not compressed: the source archives in it are compressed already.

`check` fails unless the archive holds `SOURCES.txt` and every file it lists (size and SHA-256 as
listed, and no other file in `sources/`), the two SBOMs, the two inventories, the two notices
files, the offline-audit report, the signatures of the four packages and of the two SBOMs, and the
README. The release workflow runs it through `tools.release_notes complete`.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import re
import subprocess
import sys
import tarfile
from collections.abc import Iterable
from pathlib import Path
from typing import IO

ROOT = Path(__file__).resolve().parents[1]
REPO_SLUG = "0h3xn4/wireviz_harness-design-studio"
FORMATS = ("linux", "windows")
FOLDERS = ("sources", "sbom", "inventory", "notices", "offline-audit", "signatures")
PACKAGE_NAMES = (
    "harness-design-studio_{v}_amd64.deb",
    "harness-design-studio-{v}-linux-x86_64.tar.gz",
    "harness-design-studio-{v}-windows-x86_64-setup.exe",
    "harness-design-studio-{v}-windows-x86_64.zip",
)
COSIGN_IDENTITY = (
    "--certificate-identity-regexp '(?i)^https://github.com/0h3xn4/wireviz_harness-design-studio/"
    "\\.github/workflows/release\\.yml@refs/tags/v' "
    "--certificate-oidc-issuer https://token.actions.githubusercontent.com"
)


def bundle_name(version: str) -> str:
    """The file name of the release bundle of `version`."""
    return f"harness-design-studio-{version}-release-bundle.tar"


def top_folder(version: str) -> str:
    return bundle_name(version).removesuffix(".tar")


def package_names(version: str) -> list[str]:
    return [name.format(v=version) for name in PACKAGE_NAMES]


def required(version: str) -> dict[str, list[str]]:
    """The files each folder must hold (besides the sources that SOURCES.txt lists)."""
    sboms = [f"sbom-{version}-{f}.cdx.json" for f in FORMATS]
    return {
        "sources": ["SOURCES.txt"],
        "sbom": sboms,
        "inventory": [
            f"third-party-inventory-{version}-{f}.{ext}" for f in FORMATS for ext in ("json", "md")
        ],
        "notices": [f"THIRD_PARTY_NOTICES-{f}.txt" for f in FORMATS],
        "offline-audit": [f"offline-audit-{version}.json", f"offline-audit-{version}.md"],
        "signatures": sorted(f"{name}.sigstore.json" for name in package_names(version) + sboms),
    }


def readme(version: str) -> str:
    deb = package_names(version)[0]
    return f"""Harness Design Studio {version}: release bundle
{"=" * 60}

This archive holds everything on the release page of version {version} except the four packages,
SHA256SUMS and its signature. You do not need it to install the program. SHA256SUMS on the release page lists
the SHA-256 of this archive, and SHA256SUMS is signed (SHA256SUMS.sigstore.json, on the release
page).

Folders
-------

sources/        The corresponding source of the LGPL and GPL components of the packages: Qt for
                Python, Qt (qtbase, qtsvg, qtwayland) and the Ubuntu source packages of the
                libraries in the Linux packages. SOURCES.txt lists every file with its size and
                SHA-256. This is the source that THIRD_PARTY_NOTICES.txt in each package offers.
sbom/           The software bill of materials of each package format (CycloneDX JSON).
inventory/      The inventory of the third-party components of each package format (JSON and
                Markdown), made from the built package.
notices/        The third-party notices of each package format (the same text as
                THIRD_PARTY_NOTICES.txt inside the package).
offline-audit/  The report of the offline audit of the Linux .tar.gz package (Markdown and JSON).
signatures/     The Sigstore signatures (<file>.sigstore.json) of the four packages and of the
                two SBOMs, made by the release workflow without a key.

Check a package with cosign
---------------------------

Put the package and its signature side by side in one folder, for example:

    cp {top_folder(version)}/signatures/{deb}.sigstore.json .

then run (install cosign first, https://docs.sigstore.dev/):

    cosign verify-blob --bundle {deb}.sigstore.json \\
      {COSIGN_IDENTITY} \\
      {deb}

cosign prints "Verified OK" when the signature is valid. The same command checks the other
packages, and the SBOMs with their signatures in signatures/. A valid signature shows that the
file was made by the release workflow of {REPO_SLUG} for a version tag, not who wrote the code.

The build provenance attestation
--------------------------------

The packages and SHA256SUMS also have a build provenance attestation, kept by GitHub and not in
this archive. It is checked on its own, with the GitHub command line tool:

    gh attestation verify {deb} --repo {REPO_SLUG}

The steps for each platform are in docs/INSTALL.md of the repository, at the tag v{version}.
"""


def _epoch() -> int:
    if os.environ.get("SOURCE_DATE_EPOCH"):
        return int(os.environ["SOURCE_DATE_EPOCH"])
    out = subprocess.run(  # noqa: S603 - fixed arguments, no shell
        ["git", "log", "-1", "--format=%ct"],  # noqa: S607 - git from the PATH, as tools.build_deb
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    return int(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else 0


def contents(dist: Path, version: str) -> dict[str, Path]:
    """Path in the bundle (below the top folder) -> file on disk, from the folder `dist`."""
    legal = dist / "legal"
    picked: dict[str, Path] = {}

    def add(folder: str, files: Iterable[Path]) -> None:
        for path in files:
            if path.is_file():
                picked[f"{folder}/{path.name}"] = path

    add("sources", (dist / "sources").glob("*") if (dist / "sources").is_dir() else ())
    add("sbom", legal.glob(f"sbom-{version}-*.cdx.json"))
    add("inventory", legal.glob(f"third-party-inventory-{version}-*"))
    add("notices", legal.glob("THIRD_PARTY_NOTICES-*.txt"))
    add("offline-audit", dist.glob(f"offline-audit-{version}.*"))
    add("signatures", dist.glob("*.sigstore.json"))
    return picked


def _info(name: str, mtime: int, *, folder: bool = False, size: int = 0) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE if folder else tarfile.REGTYPE
    info.mode = 0o755 if folder else 0o644
    info.size = 0 if folder else size
    info.mtime = mtime
    info.uid = info.gid = 0
    info.uname = info.gname = "root"
    return info


def build(dist: Path, version: str, out: Path, mtime: int | None = None) -> Path:
    """Write the bundle of `version` from `dist` to `out` (see the module text)."""
    stamp = _epoch() if mtime is None else mtime
    top = top_folder(version)
    files = contents(dist, version)
    text = readme(version).encode("utf-8")
    names = sorted({*files, "README.txt"})
    folders = sorted({top, *(f"{top}/{n.rsplit('/', 1)[0]}" for n in names if "/" in n)})
    out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out, "w", format=tarfile.GNU_FORMAT) as tar:
        entries = [(f, None) for f in folders] + [(f"{top}/{n}", n) for n in names]
        for arcname, name in sorted(entries):
            if name is None:
                tar.addfile(_info(arcname, stamp, folder=True))
            elif name == "README.txt":
                tar.addfile(_info(arcname, stamp, size=len(text)), io.BytesIO(text))
            else:
                path = files[name]
                with path.open("rb") as handle:
                    tar.addfile(_info(arcname, stamp, size=path.stat().st_size), handle)
    return out


def _sha256(handle: IO[bytes]) -> str:
    h = hashlib.sha256()
    for block in iter(lambda: handle.read(1 << 20), b""):
        h.update(block)
    return h.hexdigest()


def parse_sources(text: str) -> list[tuple[str, int, str]]:
    """(name, bytes, sha256) of every row of SOURCES.txt (tab-separated, one heading line)."""
    rows = []
    for line in text.splitlines()[1:]:
        fields = line.split("\t")
        if len(fields) == 3 and fields[1].isdigit():
            rows.append((fields[0], int(fields[1]), fields[2].lower()))
    return rows


def problems(path: Path, version: str) -> list[str]:
    """What the bundle at `path` lacks or holds wrongly; an empty list when it is complete."""
    if not path.is_file():
        return [f"{path.name}: no such file"]
    top = top_folder(version)
    found: list[str] = []
    with tarfile.open(path, "r:") as tar:
        members = {m.name: m for m in tar.getmembers()}
        for name, member in members.items():
            parts = name.split("/")
            if parts[0] != top or ".." in parts or name.startswith("/"):
                found.append(f"an entry outside the folder {top}/: {name}")
            elif not (member.isfile() or member.isdir()):
                found.append(f"not a plain file or folder: {name}")
        files = {name.removeprefix(f"{top}/"): m for name, m in members.items() if m.isfile()}
        if "README.txt" not in files:
            found.append("README.txt is missing")
        for folder, names in required(version).items():
            for name in names:
                if f"{folder}/{name}" not in files:
                    found.append(f"{folder}/{name} is missing")
        listing = files.get("sources/SOURCES.txt")
        if listing is not None:
            handle = tar.extractfile(listing)
            rows = parse_sources(handle.read().decode("utf-8")) if handle else []
            if not rows:
                found.append("sources/SOURCES.txt lists no file")
            listed = {name for name, _, _ in rows}
            for name, size, digest in rows:
                source = files.get(f"sources/{name}")
                if source is None:
                    found.append(f"sources/{name} (listed in SOURCES.txt) is missing")
                    continue
                data = tar.extractfile(source)
                if source.size != size or data is None or _sha256(data) != digest:
                    found.append(
                        f"sources/{name} does not match its size or SHA-256 in SOURCES.txt"
                    )
            extra = sorted(
                n
                for n in files
                if n.startswith("sources/")
                and n != "sources/SOURCES.txt"
                and n.removeprefix("sources/") not in listed
            )
            found += [f"{n} is not listed in SOURCES.txt" for n in extra]
        unknown = sorted(
            n for n in files if n != "README.txt" and n.split("/", 1)[0] not in FOLDERS
        )
        found += [f"{n} is in no folder of the bundle" for n in unknown]
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="write the bundle from the release folder DIST")
    b.add_argument("dist", type=Path)
    b.add_argument("--version", required=True)
    b.add_argument("--out", type=Path, help="default: DIST/<the bundle name>")
    c = sub.add_parser("check", help="check that a bundle holds everything it must")
    c.add_argument("bundle", type=Path)
    c.add_argument("--version", required=True)
    args = ap.parse_args(argv)
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:rc\d+)?", args.version):
        print(f"error: not a version: {args.version}", file=sys.stderr)
        return 2
    if args.cmd == "build":
        out = build(args.dist, args.version, args.out or args.dist / bundle_name(args.version))
        target = out
    else:
        target = args.bundle
    found = problems(target, args.version)
    for item in found:
        print(f"error: {item}", file=sys.stderr)
    if not found:
        with tarfile.open(target, "r:") as tar:
            count = sum(1 for m in tar.getmembers() if m.isfile())
        print(f"{target.name}: {count} files, complete")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
