"""Desktop integration: register Suketchi with the OS's app launcher.

pip/wheel installs cannot run arbitrary post-install code, so there is no
hook to create a Start Menu / Applications-menu entry at ``pip install``
time. Instead, :func:`install_shortcut` is called once from :func:`suketchi.
app.main` and creates the entry (with icon) the first time the app actually
runs, which is the practical equivalent from the user's point of view.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

APP_NAME = "Suketchi"
APP_DESCRIPTION = "A lightweight, free, and open-source PDF reader and editor."


def _icon_path() -> Optional[str]:
    from .app import asset_path

    if sys.platform == "darwin":
        names = ("suketchi.icns",)
    elif sys.platform.startswith("win"):
        names = ("suketchi.ico",)
    else:
        names = ("png/icon_256.png", "icon_256.png")

    for name in names:
        path = asset_path(name)
        if path:
            return str(path)
    return None


def _executable() -> str:
    exe = Path(sys.executable)
    if sys.platform.startswith("win"):
        pythonw = exe.with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
    return sys.executable


def _marker_file() -> Path:
    return Path.home() / ".suketchi" / "desktop_shortcut_installed"


def install_shortcut(force: bool = False) -> bool:
    """Create a Desktop/Applications-menu entry for Suketchi, once.

    Safe to call unconditionally: does nothing (and returns False) if a
    shortcut was already installed, if ``pyshortcuts`` is unavailable, or if
    shortcut creation fails for any reason (read-only home directory,
    headless CI, sandboxed environment, ...). This is a nice-to-have, never
    a requirement for running the app.
    """
    marker = _marker_file()
    if marker.exists() and not force:
        return False

    try:
        from pyshortcuts import make_shortcut
    except ImportError:
        return False

    try:
        make_shortcut(
            "-m suketchi",
            name=APP_NAME,
            description=APP_DESCRIPTION,
            icon=_icon_path(),
            executable=_executable(),
            terminal=False,
        )
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        return True
    except Exception:
        return False
