"""The parts of the card's look a person can make their own, and where they are stored."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path

_HEX = re.compile(r"\A#?([0-9A-Fa-f]{6})\Z")


@dataclass(frozen=True)
class HexColor:
    """An opaque sRGB color that reads and writes itself as `#RRGGBB`."""

    red: float
    green: float
    blue: float

    def __post_init__(self) -> None:
        # Clamp to 0...1 and round to the nearest of the 256 levels hex can express, so a
        # color survives a round trip through `hex` unchanged.
        for name, value in (("red", self.red), ("green", self.green), ("blue", self.blue)):
            object.__setattr__(self, name, round(min(max(value, 0.0), 1.0) * 255) / 255)

    @classmethod
    def from_hex(cls, text: str) -> HexColor | None:
        """Parses `#RRGGBB` or `RRGGBB`, with surrounding spaces allowed. None if it is neither."""
        match = _HEX.match(text.strip())
        if match is None:
            return None
        value = int(match.group(1), 16)
        return cls((value >> 16 & 0xFF) / 255, (value >> 8 & 0xFF) / 255, (value & 0xFF) / 255)

    @property
    def hex(self) -> str:
        return "#%02X%02X%02X" % (
            round(self.red * 255), round(self.green * 255), round(self.blue * 255)
        )

    def rgba(self, alpha: float = 1.0) -> str:
        """The CSS form, for the stylesheet the card is drawn with."""
        return "rgba(%d, %d, %d, %g)" % (
            round(self.red * 255), round(self.green * 255), round(self.blue * 255), alpha
        )


#: The widget's standard accent, the same cyan Claude Cockpit uses.
COCKPIT_CYAN = HexColor(0.31, 0.91, 1.0)

DEFAULT_TITLE = "GITHUB"
#: The longest title that still leaves room for the status note beside it.
MAXIMUM_TITLE_LENGTH = 14


def normalized_title(raw: str) -> str:
    """Titles are shown like every other label: trimmed and in capitals. Blank means the default."""
    trimmed = raw.strip()
    if not trimmed:
        return DEFAULT_TITLE
    return trimmed.upper()[:MAXIMUM_TITLE_LENGTH].strip()


@dataclass(frozen=True)
class CockpitAppearance:
    title: str = DEFAULT_TITLE
    #: Colors the section titles, the status note and the pull request numbers.
    accent: HexColor = COCKPIT_CYAN
    border: HexColor = COCKPIT_CYAN
    glow: HexColor = COCKPIT_CYAN

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", normalized_title(self.title))


STANDARD = CockpitAppearance()


class AppearanceStore:
    """Keeps the chosen appearance in a small JSON file that is easy to edit by hand.

    An unreadable file, or a single unreadable value in it, falls back to the default rather
    than stopping the widget: the card is the only interface, so it has to come up.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_config_path()

    def load(self) -> CockpitAppearance:
        stored = self._read()
        appearance = CockpitAppearance(title=str(stored.get("title", DEFAULT_TITLE)))
        for field in ("accent", "border", "glow"):
            raw = stored.get(f"{field}Color")
            color = HexColor.from_hex(raw) if isinstance(raw, str) else None
            if color is not None:
                appearance = replace(appearance, **{field: color})
        return appearance

    def save(self, appearance: CockpitAppearance) -> None:
        # Everything else in the file is kept, so writing one setting never drops another
        # the person edited by hand.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write({
            **self._read(),
            "title": appearance.title,
            "accentColor": appearance.accent.hex,
            "borderColor": appearance.border.hex,
            "glowColor": appearance.glow.hex,
        })

    def load_placement(self) -> tuple[int, int]:
        """The card's distance from the top and right edges, in pixels."""
        stored = self._read()
        return (
            _as_int(stored.get("marginTop"), DEFAULT_MARGIN),
            _as_int(stored.get("marginRight"), DEFAULT_MARGIN),
        )

    def save_placement(self, top: int, right: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write({**self._read(), "marginTop": int(top), "marginRight": int(right)})

    def reset(self) -> None:
        """Puts the title and the three colors back to their defaults.

        Only those: the position and the chosen CLI are not part of the look, so Reset to
        Defaults does not move the card or sign it in to another account.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        kept = {k: v for k, v in self._read().items() if k not in _APPEARANCE_KEYS}
        self._write(kept)

    @property
    def has_offered_customization(self) -> bool:
        """Whether the Personalize window has already been shown once, on a first launch."""
        return self._read().get("hasOfferedCustomization") is True

    @has_offered_customization.setter
    def has_offered_customization(self, value: bool) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write({**self._read(), "hasOfferedCustomization": bool(value)})

    def load_cli_command(self) -> str:
        """The GitHub CLI to run; a wrapper selecting another account can be named here."""
        stored = self._read().get("cliCommand")
        return stored if isinstance(stored, str) and stored.strip() else DEFAULT_CLI_COMMAND

    def _read(self) -> dict:
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def _write(self, payload: dict) -> None:
        # Written through a temporary file, so an interrupted save cannot leave a half file
        # that the next launch would read as no configuration at all.
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)


DEFAULT_MARGIN = 12
DEFAULT_CLI_COMMAND = "gh"
#: What `reset` clears; everything else in the file is kept.
_APPEARANCE_KEYS = frozenset({"title", "accentColor", "borderColor", "glowColor"})


def config_home() -> Path:
    """The directory `XDG_CONFIG_HOME` names.

    The specification says a value that is unset, empty or relative is to be ignored, so
    those give `~/.config`.
    """
    value = os.environ.get("XDG_CONFIG_HOME", "")
    return Path(value) if os.path.isabs(value) else Path.home() / ".config"


def default_config_path() -> Path:
    return config_home() / "github-cockpit" / "config.json"


def _as_int(value: object, fallback: int) -> int:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else fallback
