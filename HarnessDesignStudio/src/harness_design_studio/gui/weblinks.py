# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The links of parts and connector sources (3.0.0, design of the harness plan section 10): the
editor never opens them in a browser (the owner's decision of 2026-11-18, "Never open browser at
all"). A click on *Copy link* puts the saved link on the clipboard, so that a person can paste it
where they choose.

Only a link the model's own rule accepts (`devices.check_web_link`: `https://` or `http://`, no
spaces, at most 2000 characters) is copied; any other text is not, and the caller gets False. This
module does not use `QDesktopServices` (`tests/test_security.py`).
"""

from collections.abc import Callable

from PySide6.QtGui import QGuiApplication

from harness_design_studio.core.devices import check_web_link
from harness_design_studio.core.edit import EditError


def web_link(link: object) -> str | None:
    """`link` as the model stores a web link, or None when it is not one."""
    try:
        return check_web_link(link, "The link")
    except EditError:
        return None


def system_clipboard(text: str) -> None:
    """Put `text` on the system clipboard (the default; tests pass their own)."""
    clipboard = QGuiApplication.clipboard()
    if clipboard is not None:
        clipboard.setText(text)


def copy_web_link(link: object, put: Callable[[str], None] = system_clipboard) -> bool:
    """Copy `link` to the clipboard when it is a web link the model accepts; False otherwise."""
    text = web_link(link)
    if text is None:
        return False
    put(text)
    return True
