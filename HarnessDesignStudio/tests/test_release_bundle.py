# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""D-232: from 2.0.1 on the release page carries the four packages, SHA256SUMS, its signature and
one release bundle with everything else (tools/release_bundle.py, tools/release_notes.py)."""

from __future__ import annotations

import hashlib
import re
import tarfile
from pathlib import Path

import pytest

from tools import gen_scf, release_bundle, release_notes

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT.parent / ".github" / "workflows"
V = "2.0.1"


def _fake_dist(tmp_path: Path, version: str = V) -> Path:
    """A release folder as the release job has it before the bundle is built."""
    dist = tmp_path / "dist"
    (dist / "legal").mkdir(parents=True)
    (dist / "sources").mkdir()
    for name in release_bundle.package_names(version):
        (dist / name).write_bytes(f"package {name}".encode())
        (dist / f"{name}.sigstore.json").write_text('{"sig": 1}\n', encoding="utf-8")
    for fmt in release_bundle.FORMATS:
        sbom = f"sbom-{version}-{fmt}.cdx.json"
        (dist / "legal" / sbom).write_text('{"bomFormat": "CycloneDX"}\n', encoding="utf-8")
        (dist / f"{sbom}.sigstore.json").write_text('{"sig": 2}\n', encoding="utf-8")
        for ext in ("json", "md"):
            (dist / "legal" / f"third-party-inventory-{version}-{fmt}.{ext}").write_text(
                f"inventory {fmt}\n", encoding="utf-8"
            )
        (dist / "legal" / f"THIRD_PARTY_NOTICES-{fmt}.txt").write_text(
            "NOTICES\n", encoding="utf-8"
        )
    rows = ["name\tbytes\tsha256"]
    for name, data in (("qtbase-everywhere-src-6.11.2.tar.xz", b"qt"), ("zlib_1.3.dsc", b"dsc")):
        (dist / "sources" / name).write_bytes(data)
        rows.append(f"{name}\t{len(data)}\t{hashlib.sha256(data).hexdigest()}")
    (dist / "sources" / "SOURCES.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")
    for ext in ("md", "json"):
        (dist / f"offline-audit-{version}.{ext}").write_text("Result: PASS\n", encoding="utf-8")
    return dist


def _members(path: Path) -> list[tarfile.TarInfo]:
    with tarfile.open(path, "r:") as tar:
        return tar.getmembers()


# ---- the bundle -----------------------------------------------------------------------------------


def test_the_bundle_holds_every_folder_and_a_readme(tmp_path: Path) -> None:
    dist = _fake_dist(tmp_path)
    out = release_bundle.build(dist, V, dist / release_bundle.bundle_name(V), mtime=1_700_000_000)
    assert out.name == "harness-design-studio-2.0.1-release-bundle.tar"
    top = "harness-design-studio-2.0.1-release-bundle"
    files = {m.name.removeprefix(f"{top}/") for m in _members(out) if m.isfile()}
    assert files == {
        "README.txt",
        "sources/SOURCES.txt",
        "sources/qtbase-everywhere-src-6.11.2.tar.xz",
        "sources/zlib_1.3.dsc",
        "sbom/sbom-2.0.1-linux.cdx.json",
        "sbom/sbom-2.0.1-windows.cdx.json",
        "inventory/third-party-inventory-2.0.1-linux.json",
        "inventory/third-party-inventory-2.0.1-linux.md",
        "inventory/third-party-inventory-2.0.1-windows.json",
        "inventory/third-party-inventory-2.0.1-windows.md",
        "notices/THIRD_PARTY_NOTICES-linux.txt",
        "notices/THIRD_PARTY_NOTICES-windows.txt",
        "offline-audit/offline-audit-2.0.1.json",
        "offline-audit/offline-audit-2.0.1.md",
        *(f"signatures/{n}.sigstore.json" for n in release_bundle.package_names(V)),
        "signatures/sbom-2.0.1-linux.cdx.json.sigstore.json",
        "signatures/sbom-2.0.1-windows.cdx.json.sigstore.json",
    }
    # the packages themselves are not in it: they are on the page
    assert not any(n.endswith((".deb", ".exe", ".zip", "x86_64.tar.gz")) for n in files)
    # the sources are copied byte for byte
    with tarfile.open(out, "r:") as tar:
        member = tar.extractfile(f"{top}/sources/zlib_1.3.dsc")
        assert member is not None and member.read() == b"dsc"
        readme = tar.extractfile(f"{top}/README.txt")
        assert readme is not None
        text = readme.read().decode("utf-8")
    for folder in release_bundle.FOLDERS:
        assert f"\n{folder}/" in text, folder
    assert "cosign verify-blob --bundle harness-design-studio_2.0.1_amd64.deb.sigstore.json" in text
    assert "side by side" in text and "gh attestation verify" in text and "on its own" in text
    assert release_bundle.problems(out, V) == []


def test_the_bundle_is_reproducible(tmp_path: Path) -> None:
    """Sorted entries, one fixed time, owner 0, fixed modes, GNU format without pax headers: the
    same files give the same bytes, whatever the times and the order on disk."""
    dist = _fake_dist(tmp_path)
    a = release_bundle.build(dist, V, tmp_path / "a.tar", mtime=1_700_000_000)
    for path in sorted(dist.rglob("*"), reverse=True):
        path.touch()  # other times on disk
    (dist / "sources" / "zlib_1.3.dsc").chmod(0o600)  # another mode on disk
    b = release_bundle.build(dist, V, tmp_path / "b.tar", mtime=1_700_000_000)
    assert a.read_bytes() == b.read_bytes()
    members = _members(a)
    names = [m.name for m in members]
    assert names == sorted(names)
    assert {m.mtime for m in members} == {1_700_000_000}
    assert {(m.uid, m.gid, m.uname, m.gname) for m in members} == {(0, 0, "root", "root")}
    assert {m.mode for m in members if m.isfile()} == {0o644}
    assert {m.mode for m in members if m.isdir()} == {0o755}
    assert all(not m.pax_headers for m in members)
    assert b"PaxHeader" not in a.read_bytes() and b"atime=" not in a.read_bytes()
    # a plain tar: not compressed (the sources are compressed already)
    assert not a.read_bytes().startswith((b"\x1f\x8b", b"\xfd7zXZ", b"BZh"))


def test_the_time_of_the_bundle_comes_from_source_date_epoch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dist = _fake_dist(tmp_path)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1234567890")
    out = release_bundle.build(dist, V, tmp_path / "x.tar")
    assert {m.mtime for m in _members(out)} == {1234567890}


@pytest.mark.parametrize(
    ("remove", "message"),
    [
        ("sources/SOURCES.txt", "sources/SOURCES.txt is missing"),
        ("sources/zlib_1.3.dsc", "sources/zlib_1.3.dsc (listed in SOURCES.txt) is missing"),
        ("legal/sbom-2.0.1-windows.cdx.json", "sbom/sbom-2.0.1-windows.cdx.json is missing"),
        ("legal/THIRD_PARTY_NOTICES-linux.txt", "notices/THIRD_PARTY_NOTICES-linux.txt is missing"),
        ("offline-audit-2.0.1.md", "offline-audit/offline-audit-2.0.1.md is missing"),
        ("offline-audit-2.0.1.json", "offline-audit/offline-audit-2.0.1.json is missing"),
        (
            "harness-design-studio_2.0.1_amd64.deb.sigstore.json",
            "signatures/harness-design-studio_2.0.1_amd64.deb.sigstore.json is missing",
        ),
        (
            "legal/third-party-inventory-2.0.1-linux.json",
            "inventory/third-party-inventory-2.0.1-linux.json is missing",
        ),
    ],
)
def test_the_check_names_what_the_bundle_lacks(tmp_path: Path, remove: str, message: str) -> None:
    dist = _fake_dist(tmp_path)
    (dist / remove).unlink()
    out = release_bundle.build(dist, V, tmp_path / "x.tar", mtime=0)
    assert message in release_bundle.problems(out, V)
    assert release_bundle.main(["check", str(out), "--version", V]) == 1


def test_the_check_compares_the_sources_with_their_list(tmp_path: Path) -> None:
    dist = _fake_dist(tmp_path)
    (dist / "sources" / "zlib_1.3.dsc").write_bytes(b"DSC")  # same size, other bytes
    (dist / "sources" / "stray.tar.xz").write_bytes(b"x")  # not in SOURCES.txt
    out = release_bundle.build(dist, V, tmp_path / "x.tar", mtime=0)
    found = release_bundle.problems(out, V)
    assert "sources/zlib_1.3.dsc does not match its size or SHA-256 in SOURCES.txt" in found
    assert "sources/stray.tar.xz is not listed in SOURCES.txt" in found
    empty = tmp_path / "empty"
    (empty / "sources").mkdir(parents=True)
    (empty / "sources" / "SOURCES.txt").write_text("name\tbytes\tsha256\n", encoding="utf-8")
    out = release_bundle.build(empty, V, tmp_path / "y.tar", mtime=0)
    assert "sources/SOURCES.txt lists no file" in release_bundle.problems(out, V)


def test_the_check_refuses_entries_outside_the_top_folder(tmp_path: Path) -> None:
    dist = _fake_dist(tmp_path)
    out = release_bundle.build(dist, V, tmp_path / "x.tar", mtime=0)
    with tarfile.open(out, "a:") as tar:
        tar.add(dist / "sources" / "SOURCES.txt", arcname="../evil.txt")
    assert any("outside the folder" in p for p in release_bundle.problems(out, V))
    assert release_bundle.problems(tmp_path / "none.tar", V) == ["none.tar: no such file"]


def test_the_command_line_builds_and_checks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    dist = _fake_dist(tmp_path)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    assert release_bundle.main(["build", str(dist), "--version", V]) == 0
    out = dist / release_bundle.bundle_name(V)
    assert out.is_file() and "complete" in capsys.readouterr().out
    assert release_bundle.main(["check", str(out), "--version", V]) == 0
    assert release_bundle.main(["check", str(out), "--version", "2.0.2"]) == 1
    assert release_bundle.main(["check", str(out), "--version", "x"]) == 2


# ---- SHA256SUMS and the complete check -------------------------------------------------------------


def test_sha256sums_lists_the_bundle(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "src").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "x"\nversion = "{V}"\ndependencies = []\n'
        "[project.optional-dependencies]\ngui = []\n",
        encoding="utf-8",
    )
    dist = _fake_dist(tmp_path)
    release_bundle.build(dist, V, dist / release_bundle.bundle_name(V), mtime=0)
    delivered = gen_scf.build_scf(root, dist)["deliverables"]
    assert isinstance(delivered, dict)
    assert sorted(delivered) == sorted(
        [*release_bundle.package_names(V), release_bundle.bundle_name(V)]
    )


def _sums(names: list[str]) -> str:
    return "".join(f"{'e' * 64}  {n}\n" for n in sorted(names))


def test_complete_needs_every_package_and_from_2_0_1_the_bundle() -> None:
    packages = release_bundle.package_names(V)
    bundle = release_bundle.bundle_name(V)
    assert release_notes.missing_files(V, [*packages, bundle]) == []
    assert release_notes.missing_files(V, packages) == [bundle]
    assert release_notes.missing_files(V, [*packages[1:], bundle]) == [
        "harness-design-studio_2.0.1_amd64.deb"
    ]
    # 2.0.0 and older have no bundle and do not need one
    old = release_bundle.package_names("2.0.0")
    assert release_notes.missing_files("2.0.0", old) == []
    assert not release_notes.is_bundled("2.0.0") and not release_notes.is_bundled("1.17.1")
    assert release_notes.is_bundled("2.0.1") and release_notes.is_bundled("2.0.1rc1")
    assert release_notes.is_bundled("2.1.0") and release_notes.is_bundled("10.0.0")


def test_complete_checks_the_content_of_the_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dist = _fake_dist(tmp_path)
    monkeypatch.setattr(release_notes, "project_version", lambda root=None: V)
    names = [*release_bundle.package_names(V), release_bundle.bundle_name(V)]
    (dist / "SHA256SUMS").write_text(_sums(names), encoding="utf-8")
    # listed, but not there
    assert release_notes.main(["complete", str(dist / "SHA256SUMS")]) == 1
    assert "no such file" in capsys.readouterr().err
    release_bundle.build(dist, V, dist / release_bundle.bundle_name(V), mtime=0)
    assert release_notes.main(["complete", str(dist / "SHA256SUMS")]) == 0
    # a bundle without the audit report stops the release
    (dist / f"offline-audit-{V}.json").unlink()
    release_bundle.build(dist, V, dist / release_bundle.bundle_name(V), mtime=0)
    assert release_notes.main(["complete", str(dist / "SHA256SUMS")]) == 1
    assert "offline-audit/offline-audit-2.0.1.json is missing" in capsys.readouterr().err
    # SHA256SUMS without the bundle
    (dist / "SHA256SUMS").write_text(_sums(names[:-1]), encoding="utf-8")
    assert release_notes.main(["complete", str(dist / "SHA256SUMS")]) == 1
    assert "no file harness-design-studio-2.0.1-release-bundle.tar" in capsys.readouterr().err


# ---- the page text ---------------------------------------------------------------------------------


def _page(version: str, names: list[str]) -> str:
    return release_notes.notes(version, f"## {version}\n\nFirst.\n", _sums(names), "Highlights.")


def test_the_page_of_2_0_1_points_to_the_bundle_and_the_signature_of_sha256sums() -> None:
    names = [*release_bundle.package_names(V), release_bundle.bundle_name(V)]
    text = _page(V, names)
    download = text.split("## Download", 1)[1].split("## What is new", 1)[0]
    # the download table lists the four packages, not the bundle
    rows = [ln for ln in download.splitlines() if ln.startswith("| ") and "`" in ln]
    assert len(rows) == 4 and not any("release-bundle" in r for r in rows)
    assert (
        "Everything else is in one archive, `harness-design-studio-2.0.1-release-bundle.tar`"
        in (download)
    )
    for what in ("source of the LGPL and GPL components", "SBOMs", "notices", "offline audit"):
        assert what in download, what
    assert "Other files" not in text
    check = text.split("## Check your download", 1)[1].split("## Status", 1)[0]
    assert "| `harness-design-studio-2.0.1-release-bundle.tar` |" in check
    assert "`SHA256SUMS` lists the four packages and the bundle" in check
    assert "`SHA256SUMS.sigstore.json`, is on this page" in check
    assert "cosign verify-blob --bundle SHA256SUMS.sigstore.json" in check
    assert "in the folder `signatures/` of the bundle" in check
    assert "gh attestation verify <file>" in check and "checked on its own" in check
    assert "sha256sum -c SHA256SUMS --ignore-missing" in check
    assert "the `.sigstore.json` file beside it" not in check


def test_the_page_of_2_0_0_keeps_its_text() -> None:
    """Releases up to 2.0.0 keep their pages; `notes_only` writes them as before (D-232)."""
    sums = (ROOT / "compliance" / "evidence" / "release_2.0.0_SHA256SUMS").read_text("utf-8")
    text = release_notes.notes("2.0.0", "## 2.0.0\n\nFirst.\n", sums, "Highlights.")
    assert "release-bundle" not in text and "SHA256SUMS.sigstore.json" not in text
    assert "Every file is also signed with Sigstore (the `.sigstore.json` file beside it)" in text
    assert "`sha256sum -c SHA256SUMS` (Linux)" in text
    assert "Other files" not in text
    # a stray bundle-like name on an old page is shown as before, as another file
    names = [*release_bundle.package_names("2.0.0"), release_bundle.bundle_name("2.0.0")]
    assert "Other files: `harness-design-studio-2.0.0-release-bundle.tar`" in _page("2.0.0", names)


# ---- the workflows ---------------------------------------------------------------------------------


def _job(text: str, name: str) -> str:
    body = text[text.index("\njobs:\n") :]
    parts = re.split(r"^  ([a-z0-9_-]+):\n", body, flags=re.M)
    return dict(zip(parts[1::2], parts[2::2], strict=True))[name]


def test_the_release_job_publishes_seven_files_and_builds_the_bundle_in_order() -> None:
    release = _job((WORKFLOWS / "release.yml").read_text(encoding="utf-8"), "release")
    steps = [
        "cosign sign-blob",  # the packages and the SBOMs, before the bundle
        "python -m tools.release_bundle build dist",
        "python -m tools.gen_scf dist",
        "python -m tools.release_notes complete dist/SHA256SUMS",
        "tools.release_notes notes",
        "cosign sign-blob --yes --bundle SHA256SUMS.sigstore.json SHA256SUMS",
        "attest-build-provenance",
        "gh release create",
    ]
    at = [release.find(step) for step in steps]
    assert all(i >= 0 for i in at), [s for s, i in zip(steps, at, strict=True) if i < 0]
    assert at == sorted(at), "sign, bundle, checksums, check, notes, sign the sums, attest, publish"
    line = next(ln for ln in release.splitlines() if ln.strip().startswith("files=("))
    published = re.findall(r"dist/\S+?(?=[ )])", line)
    assert published == [
        "dist/*.tar.gz",
        "dist/*.deb",
        "dist/*-setup.exe",
        "dist/*.zip",
        "dist/SHA256SUMS",
        "dist/SHA256SUMS.sigstore.json",
        'dist/"$bundle"',
    ], published
    assert "dist/sources" not in line and "dist/legal" not in line
    assert 'test "${#files[@]}" = 7' in release
    # the attestation is as before: the packages and SHA256SUMS
    attest = release.split("attest-build-provenance", 1)[1].split("- uses:", 1)[0]
    assert "release-bundle" not in attest and "HarnessDesignStudio/dist/SHA256SUMS" in attest
    # a tag older than the bundle is not rebuilt with this workflow (its pages stay as they are)
    linux = _job((WORKFLOWS / "release.yml").read_text(encoding="utf-8"), "linux")
    assert "if [ ! -f tools/release_bundle.py ]" in linux
    assert linux.index("tools/release_bundle.py") < linux.index("tools.build_installer")


def test_the_sources_workflow_builds_the_bundle_dry_on_pull_requests() -> None:
    text = (WORKFLOWS / "harness-sources.yml").read_text(encoding="utf-8")
    on = text.split("\non:", 1)[1].split("\npermissions:", 1)[0]
    assert '"HarnessDesignStudio/tools/release_bundle.py"' in on
    assert "python -m tools.release_bundle build" in text
    assert "python -m tools.release_bundle check" in text
    assert "gh release" not in text and "contents: write" not in text and "id-token" not in text
