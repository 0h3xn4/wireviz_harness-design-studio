# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The one place where the editor hands something to the system's default program: a FOLDER,
shown in the file manager (*Reveal in folder*, *Reveal output folder*, *Open the folder after the
export*, *Show folder* after *Export diagram*).

The editor opens no browser (the owner's decisions of 2026-11-18 and 2026-11-19, D-250): the links
of parts and sources are copied to the clipboard (`gui/weblinks.py`), the user guide is shown in a
window of the program (`gui/guide_window.py`), and an exported file is not opened either: *Copy
path* puts its path on the clipboard. What is left is a folder, which the system shows in its file
manager. `reveal_folder` hands over an existing local directory and nothing else: no file (which
the system would open with a program, or run), no web address, no other scheme.

    folders.reveal_folder(path)            # the QUrl handed to the system, or None (refused)
    folders.reveal_folder(path, recorder)  # tests pass their own stand-in for the system

This is the only module of the program that uses `QDesktopServices` (`tests/test_security.py`).
"""

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

SystemOpener = Callable[[QUrl], bool]


def system_open(url: QUrl) -> bool:
    """Hand `url` to the system (the default of `reveal_folder`; only a folder's URL gets here)."""
    return QDesktopServices.openUrl(url)


def folder_of(path: Path) -> Path:
    """The folder that shows `path`: the path itself when it is a folder, else its parent folder
    (Linux file managers have no portable "select this file", so the folder is shown)."""
    return path if path.is_dir() else path.parent


def folder_url(target: Path | str | QUrl) -> QUrl | None:
    """The local URL of `target` when it is an existing local directory; None for anything else
    (a file, a path that does not exist, a web address or any other URL that is not local)."""
    if isinstance(target, QUrl):
        if not target.isLocalFile() or target.hasQuery() or target.hasFragment():
            return None
        path = Path(target.toLocalFile())
    else:
        text = str(target)
        if not text or "://" in text:
            return None
        path = Path(text)
    try:
        if not path.is_dir():
            return None
    except OSError, ValueError:
        return None
    return QUrl.fromLocalFile(str(path.absolute()))


def reveal_folder(target: Path | str | QUrl, opener: SystemOpener = system_open) -> QUrl | None:
    """Show the folder `target` in the file manager. Returns the URL handed to `opener`, or None
    when `target` is not an existing local directory (then nothing is handed over)."""
    url = folder_url(target)
    if url is None:
        return None
    opener(url)
    return url
