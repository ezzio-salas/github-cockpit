"""Polls GitHub for open pull requests and keeps the card showing the latest good reading."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from cockpit_core.appearance import AppearanceStore
from cockpit_core.pr_fetcher import (
    CliNotFound,
    CommandFailed,
    FetchError,
    NotAuthenticated,
    PullRequestFetcher,
    TimedOut,
)
from cockpit_core.pull_request import ParseError, parse
from cockpit_core.relative_time import compact

from . import fonts
from .panel import CockpitPanel
from .pr_row import open_uri
from .view import CockpitSnapshot, Section

log = logging.getLogger(__name__)

APPLICATION_ID = "local.github-cockpit"
REFRESH_INTERVAL = 60
#: Ages move on without a fetch.
REDRAW_INTERVAL = 30
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
