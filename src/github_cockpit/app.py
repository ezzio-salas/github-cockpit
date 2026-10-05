"""Polls GitHub for open pull requests and keeps the card showing the latest good reading."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from cockpit_core.appearance import AppearanceStore
from cockpit_core.comments import (
    CommentReading,
    CommentWatch,
    PullRequestComment,
    parse_comments,
)
from cockpit_core.pr_fetcher import (
    CliNotFound,
    CommandFailed,
    FetchError,
    NotAuthenticated,
    PullRequestFetcher,
    TimedOut,
)
from cockpit_core.pull_request import ParseError, parse
from cockpit_core.pull_request import PullRequest
from cockpit_core.relative_time import compact

from . import fonts
from .bubble import CommentBubble
from .panel import CockpitPanel
from .pr_row import open_uri
from .view import CockpitSnapshot, Section

log = logging.getLogger(__name__)

APPLICATION_ID = "local.github-cockpit"
REFRESH_INTERVAL = 60
#: Ages move on without a fetch.
REDRAW_INTERVAL = 30
#: How long the pointer rests on a row before its comment shows, and how long the comment
#: outlasts the pointer leaving, so sweeping across the card or crossing to the bubble does
#: not flicker.
HOVER_DELAY_MS = 350
UNHOVER_DELAY_MS = 300
_PULL_REQUESTS_URL = "https://github.com/pulls"

_MESSAGES = {
    CliNotFound: "GH CLI NOT FOUND",
    TimedOut: "TIMED OUT",
    NotAuthenticated: "NOT SIGNED IN",
    CommandFailed: "COULD NOT READ PRS",
    ParseError: "UNRECOGNIZED OUTPUT",
}


class CockpitApplication(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APPLICATION_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS
        )
        self._store = AppearanceStore()
        self._fetcher = PullRequestFetcher(command=self._store.load_cli_command())
        self._panel: CockpitPanel | None = None
        self._bubble: CommentBubble | None = None
        self._comment_watch = CommentWatch()
        #: The latest comments read, which hovering a row looks up.
        self._comments: CommentReading | None = None
        #: A new comment shown until it is dismissed; a hover preview covers it for a while,
        #: then gives way to it.
        self._announced: PullRequestComment | None = None
        #: The comment shown because the pointer rests on its row.
        self._previewed: PullRequestComment | None = None
        self._hovered: PullRequest | None = None
        self._is_pointer_on_bubble = False
        self._hover_update = 0

        #: The last reading that worked, and when it was taken. None until the first success.
        self._reading: tuple[tuple[Section, ...], datetime] | None = None
        #: Why the most recent fetch failed; None after a success.
        self._failure: str | None = None
        self._is_fetching = False

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        fonts.ensure_display_font()
        for name, handler in (
            ("refresh", lambda *_: self.refresh()),
            ("quit", lambda *_: self.quit()),
            ("open-github", lambda *_: open_uri(_PULL_REQUESTS_URL)),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            self.add_action(action)

    def do_activate(self) -> None:
        if self._panel is None:
            self._panel = CockpitPanel(self, self._store)
            self._bubble = CommentBubble(self)
            # A bubble left behind by a moved card would point at nothing.
            self._panel.on_moved = self._bubble.dismiss
            self._bubble.on_dismiss = self._on_bubble_dismissed
            self._bubble.on_hover_change = self._on_bubble_hover
            self._panel.set_on_hover_change(self._on_row_hover)
            self._panel.apply(self._store.load())
            self._render()
            self._panel.present()
            self.refresh()
            GLib.timeout_add_seconds(REFRESH_INTERVAL, self._on_refresh_tick)
            GLib.timeout_add_seconds(REDRAW_INTERVAL, self._on_redraw_tick)
        self._panel.present()

    # MARK: - Polling

    def _on_refresh_tick(self) -> bool:
        self.refresh()
        return GLib.SOURCE_CONTINUE

    def _on_redraw_tick(self) -> bool:
        self._render()
        return GLib.SOURCE_CONTINUE

    def refresh(self) -> None:
        """Starts a fetch unless one is already running, so polls never pile up."""
        if self._is_fetching:
            return
        self._is_fetching = True
        self._render()
        threading.Thread(target=self._fetch, name="fetch", daemon=True).start()

    def _fetch(self) -> None:
        """Runs off the main loop; the answer is handed back to it with `idle_add`."""
        try:
            sections = (
                Section("MINE", tuple(parse(self._fetcher.fetch_mine()))),
                Section("REVIEW", tuple(parse(self._fetcher.fetch_review_requested()))),
            )
            GLib.idle_add(self._on_fetched, sections, None)
        except (FetchError, ParseError) as error:
            GLib.idle_add(self._on_fetched, None, error)
            return
        self._fetch_comments(sections)

    def _fetch_comments(self, sections: tuple[Section, ...]) -> None:
        """Reads the latest comments once the card already shows the pull requests.

        A failure here is only logged: the card never depends on it.
        """
        node_ids = [pull.node_id for section in sections for pull in section.pulls if pull.node_id]
        if not node_ids:
            return
        try:
            reading = parse_comments(self._fetcher.fetch_comments(node_ids))
        except (FetchError, ParseError) as error:
            log.warning("Comment fetch failed: %s", error)
            return
        GLib.idle_add(self._on_comments, reading)

    def _on_comments(self, reading: CommentReading) -> bool:
        self._comments = reading
        comment = self._comment_watch.announce(reading)
        if comment is not None:
            self._announced = comment
            # A hover preview keeps the bubble until the pointer moves on; the announcement
            # follows it.
            if self._previewed is None:
                self._show_bubble(comment)
        return GLib.SOURCE_REMOVE

    # MARK: - Hover

    def _on_row_hover(self, pull: PullRequest | None) -> None:
        self._hovered = pull
        self._schedule_hover_update()

    def _on_bubble_hover(self, is_on_bubble: bool) -> None:
        self._is_pointer_on_bubble = is_on_bubble
        self._schedule_hover_update()

    def _on_bubble_dismissed(self, comment: PullRequestComment) -> None:
        if comment == self._announced:
            self._announced = None
        self._previewed = None

    def _schedule_hover_update(self) -> None:
        if self._hover_update:
            GLib.source_remove(self._hover_update)
        delay = UNHOVER_DELAY_MS if self._hovered is None else HOVER_DELAY_MS
        self._hover_update = GLib.timeout_add(delay, self._update_hover_bubble)

    def _update_hover_bubble(self) -> bool:
        """Shows the latest comment on the row under the pointer. Once the pointer is on neither
        a row with comments nor the bubble, puts back what was there before."""
        self._hover_update = 0
        hovered = None
        if self._hovered is not None and self._comments is not None:
            hovered = self._comments.latest_on(self._hovered.number, self._hovered.repo)

        if hovered is not None:
            if self._bubble is not None and hovered != self._bubble.comment:
                self._previewed = hovered
                self._show_bubble(hovered)
        elif not self._is_pointer_on_bubble and self._previewed is not None:
            self._previewed = None
            if self._announced is not None:
                self._show_bubble(self._announced)
            elif self._bubble is not None:
                self._bubble.dismiss()
        return GLib.SOURCE_REMOVE

    def _show_bubble(self, comment: PullRequestComment) -> None:
        if self._panel is None or self._bubble is None:
            return
        top, right = self._panel.placement
        self._bubble.show_comment(
            comment,
            _now(),
            card_top=top,
            card_right=right,
            anchor_y=self._panel.anchor_y(comment),
            screen_width=self._panel.screen_width(),
        )

    def _on_fetched(
        self, sections: tuple[Section, ...] | None, error: Exception | None
    ) -> bool:
        self._is_fetching = False
        if sections is not None:
            self._reading = (sections, _now())
            self._failure = None
        else:
            self._failure = _MESSAGES.get(type(error), "COULD NOT READ PRS")
            log.error("Pull request fetch failed: %s", error)
        self._render()
        return GLib.SOURCE_REMOVE

    # MARK: - Drawing

    def _render(self) -> None:
        if self._panel is None:
            return
        now = _now()
        is_stale = self._reading is not None and self._failure is not None

        if self._is_fetching:
            status = "SYNC"
        elif is_stale and self._reading is not None:
            status = f"STALE · {compact((now - self._reading[1]).total_seconds())}"
        else:
            status = ""

        self._panel.render(
            CockpitSnapshot(body=self._body(), status=status, is_stale=is_stale), now
        )

    def _body(self) -> tuple[Section, ...] | str:
        """The sections to draw, or the one message that stands in for them."""
        if self._reading is None:
            return self._failure or "READING PULL REQUESTS"
        sections = tuple(section for section in self._reading[0] if section.pulls)
        # An empty section is hidden; only when both are empty is there something to say.
        return sections or "NO OPEN PULL REQUESTS"


def _now() -> datetime:
    """Timezone-aware, because GitHub's timestamps are."""
    return datetime.now(timezone.utc)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    return CockpitApplication().run(None)
