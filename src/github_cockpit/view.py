"""The glass card: a header, then one section per list of pull requests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from cockpit_core.appearance import CockpitAppearance
from cockpit_core.pull_request import PullRequest

from . import theme
from .pr_row import PullRequestRow


@dataclass(frozen=True)
class Section:
    """A titled list of pull requests, such as `MINE` or `REVIEW`."""

    name: str
    pulls: tuple[PullRequest, ...]


@dataclass(frozen=True)
class CockpitSnapshot:
    """What the widget shows at one moment."""

    #: The sections to draw, or a single message to show in their place.
    body: tuple[Section, ...] | str
    #: Short header note such as `SYNC` or `STALE · 2m`; empty when there is nothing to report.
    status: str
    is_stale: bool


class CockpitView(Gtk.Box):
    """The card. Dragging it moves the window; clicking a row opens that pull request."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        # The glow is drawn by the card's box-shadow, which needs transparent room around it.
        self.set_margin_top(theme.GLOW_MARGIN)
        self.set_margin_bottom(theme.GLOW_MARGIN)
        self.set_margin_start(theme.GLOW_MARGIN)
        self.set_margin_end(theme.GLOW_MARGIN)

        self._title = Gtk.Label(label=CockpitAppearance().title)
        self._title.add_css_class("section-title")
        self._title.set_xalign(0)

        self._status = Gtk.Label(label="")
        self._status.add_css_class("status")
        self._status.set_halign(Gtk.Align.END)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._title.set_hexpand(True)
        header.append(self._title)
        header.append(self._status)

        self._body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        content.set_margin_top(theme.PADDING)
        content.set_margin_bottom(theme.PADDING)
        content.set_margin_start(theme.PADDING)
        content.set_margin_end(theme.PADDING)
        content.append(header)
        content.append(self._body)

        self.card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.card.add_css_class("card")
        self.card.set_size_request(theme.CARD_WIDTH, -1)
        # Without layer-shell the compositor may hand the window more room than the card
        # needs; the card keeps its own width rather than stretching to fill it.
        self.card.set_hexpand(False)
        self.card.set_vexpand(False)
        self.card.set_halign(Gtk.Align.CENTER)
        self.card.set_valign(Gtk.Align.START)
        self.card.append(content)
        self.append(self.card)
        self._rows: list[PullRequestRow] = []
        #: Reports the pull request under the pointer whenever it changes; None once it leaves
        #: the rows.
        self.on_hover_change: Callable[[PullRequest | None], None] | None = None
        self._hovered: PullRequest | None = None

        # One controller for the whole card rather than one per row: rows are rebuilt on every
        # render, and a pointer resting on a rebuilt row should not read as having left it.
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", lambda _controller, x, y: self._set_hovered(self.pull_at(x, y)))
        motion.connect("leave", lambda _controller: self._set_hovered(None))
        self.add_controller(motion)

    def pull_at(self, x: float, y: float) -> PullRequest | None:
        """The pull request whose row is at `x`, `y` in this view, if any."""
        widget = self.pick(x, y, Gtk.PickFlags.DEFAULT)
        while widget is not None and not isinstance(widget, PullRequestRow):
            widget = widget.get_parent()
        return widget.pull if widget is not None else None

    def _set_hovered(self, pull: PullRequest | None) -> None:
        if pull == self._hovered:
            return
        self._hovered = pull
        if self.on_hover_change is not None:
            self.on_hover_change(pull)

    def row_for(self, number: int, repo: str) -> PullRequestRow | None:
        """The row showing pull request `number` in `repo`, if the card shows it."""
        for row in self._rows:
            if row.pull.number == number and row.pull.repo == repo:
                return row
        return None

    def apply(self, appearance: CockpitAppearance) -> None:
        """Takes effect on the title at once; the colors arrive with the reloaded stylesheet."""
        self._title.set_text(appearance.title)

    def render(self, snapshot: CockpitSnapshot, now: datetime) -> None:
        self._status.set_text(snapshot.status)
        # An empty label still claims a line's height, which would nudge the header as the
        # status comes and goes.
        self._status.set_visible(bool(snapshot.status))
        if snapshot.is_stale:
            self._status.add_css_class("stale")
        else:
            self._status.remove_css_class("stale")

        _remove_children(self._body)
        self._rows = []
        if isinstance(snapshot.body, str):
            message = Gtk.Label(label=snapshot.body)
            message.add_css_class("message")
            message.set_xalign(0)
            self._body.append(message)
        else:
            for section in snapshot.body:
                self._body.append(self._section_view(section, now))

        # Values read before a failure stay on screen, dimmed, rather than disappearing.
        if snapshot.is_stale:
            self._body.add_css_class("stale-body")
        else:
            self._body.remove_css_class("stale-body")



    def _section_view(self, section: Section, now: datetime) -> Gtk.Widget:
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        title = Gtk.Label(label=section.name)
        title.add_css_class("section-title")
        title.set_xalign(0)
        column.append(title)

        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for pull in section.pulls:
            row = PullRequestRow(pull, now)
            self._rows.append(row)
            rows.append(row)
        column.append(rows)
        return column


def _remove_children(box: Gtk.Box) -> None:
    child = box.get_first_child()
    while child is not None:
        following = child.get_next_sibling()
        box.remove(child)
        child = following
