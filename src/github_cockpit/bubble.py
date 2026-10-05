"""A speech bubble beside the card that announces a new comment until it is dismissed."""

from __future__ import annotations

import logging
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from cockpit_core.comments import PullRequestComment  # noqa: E402
from cockpit_core.relative_time import age  # noqa: E402

from . import theme  # noqa: E402
from .panel import HAS_LAYER_SHELL, LayerShell  # noqa: E402
from .pr_row import open_uri  # noqa: E402

log = logging.getLogger(__name__)

#: The compositor sees this name, so a `layerrule` can blur behind the bubble as it does the card.
NAMESPACE = "github-cockpit-bubble"
#: Matches the `bubble-leave` animation in the stylesheet.
_LEAVE_MILLISECONDS = 220


class CommentBubble(Gtk.Window):
    """It springs out next to the comment's row and bobs gently while it is up. Its close button
    dismisses it; clicking anywhere else opens the comment and dismisses it too. A newer comment
    replaces it.

    The animations are CSS keyframes, so GTK drops them when the desktop asks for less motion.
    Without gtk4-layer-shell there is no way to place the bubble beside the card, so it is not
    shown.
    """

    def __init__(self, application: Gtk.Application) -> None:
        super().__init__(application=application)
        self.set_decorated(False)
        self.set_resizable(False)
        self.add_css_class("bubble-window")
        self._comment: PullRequestComment | None = None
        self._pop: Gtk.Widget | None = None
        self._leaving = 0

        if HAS_LAYER_SHELL:
            LayerShell.init_for_window(self)
            LayerShell.set_namespace(self, NAMESPACE)
            LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
            LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.NONE)
            LayerShell.set_anchor(self, LayerShell.Edge.TOP, True)
            LayerShell.set_anchor(self, LayerShell.Edge.RIGHT, True)

        # The close button claims its own clicks, so this one only sees the rest of the bubble.
        click = Gtk.GestureClick()
        click.connect("released", self._on_click)
        self.add_controller(click)

    def show_comment(
        self,
        comment: PullRequestComment,
        now: datetime,
        *,
        card_top: int,
        card_right: int,
        anchor_y: float,
        screen_width: int,
    ) -> None:
        """Shows `comment`, replacing any bubble already up.

        `card_top` and `card_right` are the card window's margins from the screen's top and right
        edges, `anchor_y` is the height on the card window the tail points at, and `screen_width`
        decides whether there is room on the card's left.
        """
        if not HAS_LAYER_SHELL:
            log.info("Not showing a comment bubble: it needs gtk4-layer-shell beside the card")
            return

        self._cancel_leaving()
        self._comment = comment

        # Left of the card unless that would leave the screen; then right of it.
        right = card_right + theme.CARD_WIDTH + theme.BUBBLE_GAP
        tail_on_right = right + theme.BUBBLE_WINDOW_WIDTH <= screen_width
        if not tail_on_right:
            right = max(
                0, card_right + 2 * theme.GLOW_MARGIN - theme.BUBBLE_GAP - theme.BUBBLE_WINDOW_WIDTH
            )

        anchor = card_top + anchor_y
        top = max(0, round(anchor - theme.GLOW_MARGIN - theme.BUBBLE_TAIL_OFFSET))
        tail_offset = anchor - top - theme.GLOW_MARGIN

        LayerShell.set_margin(self, LayerShell.Edge.TOP, top)
        LayerShell.set_margin(self, LayerShell.Edge.RIGHT, right)
        # A fresh widget tree restarts the CSS animations from the first frame.
        bubble = self._build(comment, now, tail_on_right=tail_on_right, tail_offset=tail_offset)
        self.set_child(bubble)
        self.present()

    def dismiss(self) -> None:
        """Plays the leaving animation, then hides."""
        if self._comment is None or self._pop is None or self._leaving:
            return
        self._pop.add_css_class("leaving")
        self._leaving = GLib.timeout_add(_LEAVE_MILLISECONDS, self._on_left)

    # MARK: - Construction

    def _build(
        self, comment: PullRequestComment, now: datetime, *, tail_on_right: bool, tail_offset: float
    ) -> Gtk.Widget:
        close = Gtk.Button.new_from_icon_name("window-close-symbolic")
        close.set_has_frame(False)
        close.set_can_focus(False)
        close.add_css_class("bubble-close")
        close.set_tooltip_text("Dismiss")
        close.connect("clicked", lambda _button: self.dismiss())

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.append(_label(f"@{comment.author}", "bubble-author", expand=True))
        header.append(_label(age(comment.created_at, now), "bubble-detail"))
        header.append(close)

        body = Gtk.Label(label=comment.text)
        body.add_css_class("bubble-text")
        body.set_xalign(0)
        body.set_wrap(True)
        body.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        body.set_lines(theme.BUBBLE_LINE_LIMIT)
        body.set_ellipsize(Pango.EllipsizeMode.END)
        body.set_max_width_chars(1)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        content.set_size_request(theme.BUBBLE_CONTENT_WIDTH, -1)
        content.append(header)
        content.append(body)
        content.append(_label(f"{comment.repo} {comment.reference}", "bubble-detail"))

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.add_css_class("bubble-card")
        card.append(content)

        # A square turned 45 degrees, half of it outside the card: only its two outer edges are
        # drawn, and they meet in a point aimed at the card.
        tail = Gtk.Box()
        tail.add_css_class("bubble-tail")
        tail.add_css_class("right" if tail_on_right else "left")
        tail.set_size_request(theme.BUBBLE_TAIL_SIZE, theme.BUBBLE_TAIL_SIZE)
        tail.set_valign(Gtk.Align.START)
        tail_top = round(tail_offset - theme.BUBBLE_TAIL_SIZE / 2)
        tail.set_margin_top(max(theme.CORNER_RADIUS, tail_top))
        inset = theme.BUBBLE_TAIL_LENGTH - theme.BUBBLE_TAIL_SIZE // 2
        if tail_on_right:
            card.set_margin_end(theme.BUBBLE_TAIL_LENGTH)
            tail.set_halign(Gtk.Align.END)
            tail.set_margin_end(inset)
        else:
            card.set_margin_start(theme.BUBBLE_TAIL_LENGTH)
            tail.set_halign(Gtk.Align.START)
            tail.set_margin_start(inset)

        shape = Gtk.Overlay()
        shape.set_child(card)
        shape.add_overlay(tail)

        # Two boxes, because the arrival and the float both animate `transform` and one widget
        # can only run one animation on a property.
        self._pop = Gtk.Box()
        self._pop.add_css_class("bubble-pop")
        self._pop.append(shape)

        float_box = Gtk.Box()
        float_box.add_css_class("bubble-float")
        float_box.set_margin_top(theme.GLOW_MARGIN)
        float_box.set_margin_bottom(theme.GLOW_MARGIN)
        float_box.set_margin_start(theme.GLOW_MARGIN)
        float_box.set_margin_end(theme.GLOW_MARGIN)
        float_box.append(self._pop)
        return float_box

    # MARK: - Events

    def _on_click(self, *_args: object) -> None:
        if self._comment is not None:
            open_uri(self._comment.url)
        self.dismiss()

    def _on_left(self) -> bool:
        self._leaving = 0
        self._comment = None
        self.set_visible(False)
        return GLib.SOURCE_REMOVE

    def _cancel_leaving(self) -> None:
        if self._leaving:
            GLib.source_remove(self._leaving)
            self._leaving = 0


def _label(text: str, style: str, *, expand: bool = False) -> Gtk.Label:
    label = Gtk.Label(label=text)
    label.add_css_class(style)
    label.set_xalign(0)
    label.set_single_line_mode(True)
    if expand:
        label.set_hexpand(True)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_max_width_chars(1)
    return label
