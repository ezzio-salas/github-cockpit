"""The card's colors and its stylesheet.

Everything visual lives here, so the widgets stay about structure. The stylesheet is
rebuilt whenever the appearance changes, which is how a new accent reaches every label at
once without touching them one by one.
"""

from __future__ import annotations

from cockpit_core.appearance import CockpitAppearance, HexColor

#: Transparent space around the card where its glow is drawn.
GLOW_MARGIN = 14
CORNER_RADIUS = 16
CARD_WIDTH = 300
PADDING = 16
#: How far the pointer travels before a press counts as moving the card rather than a click.
DRAG_THRESHOLD = 3

#: A draft pull request is dimmed rather than colored; amber is kept for a real warning.
AMBER = HexColor.from_hex("#FFB83D")
PRIMARY_TEXT = "rgba(255, 255, 255, 0.78)"
SECONDARY_TEXT = "rgba(255, 255, 255, 0.42)"
#: The same dark glass the macOS card uses, minus the blur, which the compositor adds.
SURFACE = "rgba(5, 10, 18, 0.55)"

DISPLAY_FAMILY = "Orbitron, monospace"
MONO_FAMILY = "monospace"


def stylesheet(appearance: CockpitAppearance) -> str:
    """The whole card's CSS for one appearance."""
    accent = appearance.accent
    return f"""
window.cockpit {{
    background: transparent;
}}

.card {{
    background: {SURFACE};
    border: 1px solid {appearance.border.rgba(0.45)};
    border-radius: {CORNER_RADIUS}px;
    box-shadow: 0 0 9px 0 {appearance.glow.rgba(0.55)};
}}

.section-title {{
    font-family: {DISPLAY_FAMILY};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 3px;
    color: {accent.rgba()};
}}

.status {{
    font-family: {DISPLAY_FAMILY};
    font-size: 8px;
    letter-spacing: 1.5px;
    color: {accent.rgba(0.6)};
}}

/* Amber keeps its own color whatever accent is chosen, because here the color is the warning. */
.status.stale {{
    color: {AMBER.rgba()};
}}

.message {{
    font-family: {DISPLAY_FAMILY};
    font-size: 9px;
    letter-spacing: 1.5px;
    color: {PRIMARY_TEXT};
}}

.pr-row {{
    background: none;
    border: none;
    box-shadow: none;
    outline: none;
    padding: 2px 0;
    min-height: 0;
}}

/* The only hover feedback is the title brightening, so the card stays still under the pointer. */
.pr-row:hover .pr-title {{
    color: rgba(255, 255, 255, 1);
}}

.pr-title {{
    font-size: 11.5px;
    color: {PRIMARY_TEXT};
}}

.pr-number {{
    font-family: {MONO_FAMILY};
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.5px;
    color: {accent.rgba()};
}}

.pr-repo, .pr-age {{
    font-family: {MONO_FAMILY};
    font-size: 9.5px;
    letter-spacing: 0.5px;
    color: {SECONDARY_TEXT};
}}

/* A draft reads as not-yet-real, so the whole row recedes. */
.pr-row.draft .pr-title,
.pr-row.draft .pr-number {{
    color: {SECONDARY_TEXT};
}}

.stale-body {{
    opacity: 0.45;
}}
"""
