# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The size of a file as the Export window and the Outputs panel show it. A module of its own, so
that `gui/outputs_files.py` does not import `gui/export_dialog.py` (that import closed a cycle
through `gui/lists_panel.py`)."""


def human_size(n: int) -> str:
    """ "512 B", "12.3 kB", "1.4 MB" (decimal, as file managers show)."""
    if n < 1000:
        return f"{n} B"
    if n < 1_000_000:
        return f"{n / 1000:.1f} kB"
    return f"{n / 1_000_000:.1f} MB"
