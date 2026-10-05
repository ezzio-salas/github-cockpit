"""A speech bubble beside the card that shows one comment."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

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
#: How long the link button shows a checkmark after copying.
_COPIED_FEEDBACK_MILLISECONDS = 1500


class CommentBubble(Gtk.Window):
    """It springs out next to the comment's row and bobs gently while it is up. Its close button
    dismisses it, its link button copies the comment's link, and clicking anywhere else opens the
    comment and dismisses it. Right-clicking offers the same three. Showing another comment
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
        #: Called with the comment on screen whenever the bubble goes away.
        self.on_dismiss: Callable[[PullRequestComment], None] | None = None
        #: Called with the comment's url when its link button is clicked.
        self.on_copy_link: Callable[[str], None] | None = None
        #: Called when the pointer moves onto the bubble (True) or off it (False).
        self.on_hover_change: Callable[[bool], None] | None = None
        self._pop: Gtk.Widget | None = None
        self._leaving = 0

        if HAS_LAYER_SHELL:
            LayerShell.init_for_window(self)
            LayerShell.set_namespace(self, NAMESPACE)
            LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
            LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.NONE)
            LayerShell.set_anchor(self, LayerShell.Edge.TOP, True)
            LayerShell.set_anchor(self, LayerShell.Edge.RIGHT, True)

        hover = Gtk.EventControllerMotion()
        hover.connect("enter", lambda *_: self._report_hover(True))
        hover.connect("leave", lambda *_: self._report_hover(False))
        self.add_controller(hover)

        # The close button claims its own clicks, so this one only sees the rest of the bubble.
        click = Gtk.GestureClick()
        click.connect("released", self._on_click)
        self.add_controller(click)

        secondary = Gtk.GestureClick()
        secondary.set_button(Gdk.BUTTON_SECONDARY)
        secondary.connect("pressed", self._on_secondary_press)
        self.add_controller(secondary)

        actions = Gio.SimpleActionGroup()
        for name, handler in (
            ("open", lambda *_: self._on_click()),
            ("copy-link", lambda *_: self._copy_link_from_menu()),
            ("dismiss", lambda *_: self.dismiss()),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            actions.add_action(action)
        self.insert_action_group("bubble", actions)

        menu = Gio.Menu()
        primary = Gio.Menu()
        primary.append("Open Comment", "bubble.open")
        primary.append("Copy Link", "bubble.copy-link")
        menu.append_section(None, primary)
        menu.append("Dismiss", "bubble.dismiss")
        # Hung off the window rather than its content, which is replaced for every comment.
        self._menu = Gtk.PopoverMenu.new_from_model(menu)
        self._menu.set_parent(self)
        self._menu.set_has_arrow(False)

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

    @property
    def comment(self) -> PullRequestComment | None:
        """The comment on screen; None when the bubble is hidden or leaving."""
        return None if self._leaving else self._comment

    def dismiss(self) -> None:
        """Plays the leaving animation, then hides."""
        if self._comment is None or self._pop is None or self._leaving:
            return
        if self.on_dismiss is not None:
            self.on_dismiss(self._comment)
        self._pop.add_css_class("leaving")
        self._leaving = GLib.timeout_add(_LEAVE_MILLISECONDS, self._on_left)

    # MARK: - Construction

    def _build(
        self, comment: PullRequestComment, now: datetime, *, tail_on_right: bool, tail_offset: float
    ) -> Gtk.Widget:
        copy = _icon_button("insert-link-symbolic", "Copy Link")
        copy.connect("clicked", lambda button: self._copy_link(button, comment.url))
        close = _icon_button("window-close-symbolic", "Dismiss")
        close.connect("clicked", lambda _button: self.dismiss())

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.append(_label(f"@{comment.author}", "bubble-author", expand=True))
        header.append(_label(age(comment.created_at, now), "bubble-detail"))
        header.append(copy)
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

    def _on_secondary_press(self, _gesture: Gtk.GestureClick, _n: int, x: float, y: float) -> None:
        if self._comment is None:
            return
        self._menu.set_pointing_to(Gdk.Rectangle(x=int(x), y=int(y), width=1, height=1))
        self._menu.popup()

    def _copy_link_from_menu(self) -> None:
        if self._comment is not None and self.on_copy_link is not None:
            self.on_copy_link(self._comment.url)

    def _copy_link(self, button: Gtk.Button, url: str) -> None:
        if self.on_copy_link is not None:
            self.on_copy_link(url)
        # A checkmark in the accent color confirms the copy where the eye already is.
        button.set_icon_name("object-select-symbolic")
        button.add_css_class("copied")

        def restore() -> bool:
            button.set_icon_name("insert-link-symbolic")
            button.remove_css_class("copied")
            return GLib.SOURCE_REMOVE

        GLib.timeout_add(_COPIED_FEEDBACK_MILLISECONDS, restore)

    def _report_hover(self, is_on_bubble: bool) -> None:
        if self.on_hover_change is not None:
            self.on_hover_change(is_on_bubble)

    def _on_left(self) -> bool:
        self._leaving = 0
        self._comment = None
        self.set_visible(False)
        return GLib.SOURCE_REMOVE

    def _cancel_leaving(self) -> None:
        if self._leaving:
            GLib.source_remove(self._leaving)
            self._leaving = 0


def _icon_button(icon: str, tooltip: str) -> Gtk.Button:
    """A small frameless button in the bubble's header. It claims its own clicks, so pressing it
    never also opens the comment."""
    button = Gtk.Button.new_from_icon_name(icon)
    button.set_has_frame(False)
    button.set_can_focus(False)
    button.add_css_class("bubble-button")
    button.set_tooltip_text(tooltip)
    return button


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
