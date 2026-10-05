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
#: The title row, which a bubble points at when its pull request has no row.
HEADER_HEIGHT = 14
#: How far the pointer travels before a press counts as moving the card rather than a click.
DRAG_THRESHOLD = 3

BUBBLE_CONTENT_WIDTH = 236
BUBBLE_PADDING = 12
#: How far the tail reaches out of the bubble, and the side of the square it is cut from.
BUBBLE_TAIL_LENGTH = 8
BUBBLE_TAIL_SIZE = 12
#: The tail's usual distance below the bubble's top.
BUBBLE_TAIL_OFFSET = 24
#: Space between the bubble's tail and the card.
BUBBLE_GAP = 4
BUBBLE_LINE_LIMIT = 4
BUBBLE_WINDOW_WIDTH = (
    BUBBLE_CONTENT_WIDTH + 2 * BUBBLE_PADDING + BUBBLE_TAIL_LENGTH + 2 * GLOW_MARGIN
)

#: A draft pull request is dimmed rather than colored; amber is kept for a real warning.
AMBER = HexColor.from_hex("#FFB83D")
PRIMARY_TEXT = "rgba(255, 255, 255, 0.78)"
SECONDARY_TEXT = "rgba(255, 255, 255, 0.42)"
#: The same dark glass the macOS card uses, minus the blur, which the compositor adds.
SURFACE = "rgba(5, 10, 18, 0.55)"
BUBBLE_SURFACE = "rgba(5, 10, 18, 0.92)"

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

window.bubble-window {{
    background: transparent;
}}

/* Nearly opaque, because the tail overlaps the card's edge and a thin glass would show the seam. */
.bubble-card {{
    background: {BUBBLE_SURFACE};
    border: 1px solid {appearance.border.rgba(0.45)};
    border-radius: {CORNER_RADIUS - 2}px;
    box-shadow: 0 0 9px 0 {appearance.glow.rgba(0.55)};
    padding: {BUBBLE_PADDING}px;
}}

.bubble-tail {{
    background: {BUBBLE_SURFACE};
    transform: rotate(45deg);
}}

.bubble-tail.right {{
    border-top: 1px solid {appearance.border.rgba(0.45)};
    border-right: 1px solid {appearance.border.rgba(0.45)};
}}

.bubble-tail.left {{
    border-bottom: 1px solid {appearance.border.rgba(0.45)};
    border-left: 1px solid {appearance.border.rgba(0.45)};
}}

.bubble-author {{
    font-family: {MONO_FAMILY};
    font-size: 10.5px;
    font-weight: 500;
    color: {accent.rgba()};
}}

.bubble-close {{
    min-width: 0;
    min-height: 0;
    padding: 0;
    color: {SECONDARY_TEXT};
    -gtk-icon-size: 10px;
}}

.bubble-close:hover {{
    color: rgba(255, 255, 255, 1);
}}

.bubble-text {{
    font-size: 12px;
    color: {PRIMARY_TEXT};
}}

.bubble-detail {{
    font-family: {MONO_FAMILY};
    font-size: 9.5px;
    letter-spacing: 0.5px;
    color: {SECONDARY_TEXT};
}}

/* Springs in with a small overshoot, then floats; GTK skips both when animations are turned off. */
@keyframes bubble-pop {{
    0% {{ opacity: 0; transform: scale(0.35); }}
    55% {{ opacity: 1; transform: scale(1.06); }}
    80% {{ transform: scale(0.98); }}
    100% {{ opacity: 1; transform: scale(1); }}
}}

@keyframes bubble-float {{
    from {{ transform: translateY(-1.5px); }}
    to {{ transform: translateY(1.5px); }}
}}

@keyframes bubble-leave {{
    from {{ opacity: 1; transform: scale(1); }}
    to {{ opacity: 0; transform: translateY(-6px) scale(0.85); }}
}}

.bubble-pop {{
    animation: bubble-pop 420ms ease-out;
}}

.bubble-pop.leaving {{
    animation: bubble-leave 220ms ease-in forwards;
}}

.bubble-float {{
    animation: bubble-float 1.6s ease-in-out 400ms infinite alternate;
}}
"""
