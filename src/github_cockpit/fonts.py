"""Makes the bundled Orbitron font available to fontconfig, so the card can ask for it by name."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

#: Kept in its own directory so uninstalling is one `rm -r`.
_INSTALL_DIRECTORY = Path.home() / ".local/share/fonts/github-cockpit"
_FONT = "Orbitron.ttf"


def bundled_directory() -> Path:
    """The repository's `resources/`, found relative to this file."""
    return Path(__file__).resolve().parents[2] / "resources"


def ensure_display_font() -> bool:
    """Copies Orbitron into the user's font directory if it is not already there.

    Returns whether the font should now be available. Fontconfig has no API to register a
    font for one process only, so the alternative to a user-local copy is no Orbitron at
    all; the card falls back to a monospaced font, which is legible but not the same look.
    Nothing outside `~/.local/share/fonts/github-cockpit` is touched.
    """
    source = bundled_directory() / _FONT
    if not source.is_file():
        log.warning("Bundled font missing at %s; falling back to monospace", source)
        return False

    destination = _INSTALL_DIRECTORY / _FONT
    if destination.is_file() and destination.stat().st_size == source.stat().st_size:
        return True

    try:
        _INSTALL_DIRECTORY.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        license_file = bundled_directory() / "Orbitron-OFL.txt"
        if license_file.is_file():
            shutil.copy2(license_file, _INSTALL_DIRECTORY / "Orbitron-OFL.txt")
    except OSError as error:
        log.warning("Could not install the bundled font: %s", error)
        return False

    _refresh_font_cache()
    return True


def _refresh_font_cache() -> None:
    """Without this the font is on disk but not yet visible to applications already running."""
    try:
        subprocess.run(
            ["fc-cache", "-f", str(_INSTALL_DIRECTORY)],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        log.warning("Could not refresh the font cache: %s", error)
