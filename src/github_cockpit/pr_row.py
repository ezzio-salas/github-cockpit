"""One pull request: its title and number, the repository under it, and a link to open it."""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, Gtk, Pango  # noqa: E402

from cockpit_core.pull_request import PullRequest  # noqa: E402
from cockpit_core.relative_time import age  # noqa: E402

log = logging.getLogger(__name__)


class PullRequestRow(Gtk.Button):
    """A flat, full-width button: the whole row is the link.

    It is a button so that it is focusable and reads as activatable to a screen reader, but
    it carries no frame, so visually it is two lines of text like the macOS card's rows.
    """

    def __init__(self, pull: PullRequest, now: datetime) -> None:
        super().__init__()
        self.pull = pull
        self.set_has_frame(False)
        self.set_can_focus(False)
        self.add_css_class("pr-row")
        if pull.is_draft:
            self.add_css_class("draft")
        self.set_tooltip_text(f"{pull.repo} {pull.reference} — open in your browser")

        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        column.append(_split_row(
            _label(pull.title, "pr-title", expand=True),
            _label(pull.reference, "pr-number"),
        ))
        column.append(_split_row(
            _label(pull.repo, "pr-repo", expand=True),
            _label(age(pull.updated_at, now), "pr-age"),
        ))
        self.set_child(column)

        self.connect("clicked", self._on_clicked)

    def _on_clicked(self, _button: Gtk.Button) -> None:
        open_uri(self.pull.url)


def open_uri(uri: str) -> None:
    """Opens a link in the default browser.

    The portal is tried first and `xdg-open` is the fallback, because a layer-shell surface
    is not a toplevel the portal can always parent a chooser to.
    """
    try:
        if Gio.AppInfo.launch_default_for_uri(uri, None):
            return
    except Exception as error:  # GLib.Error, and anything the portal raises underneath it
        log.warning("Portal could not open %s: %s", uri, error)

    try:
        subprocess.Popen(
            ["xdg-open", uri],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as error:
        log.error("Could not open %s: %s", uri, error)


def _label(text: str, style: str, *, expand: bool = False) -> Gtk.Label:
    label = Gtk.Label(label=text)
    label.add_css_class(style)
    label.set_xalign(0)
    label.set_single_line_mode(True)
    if expand:
        # The title gives way first; the number and the age always stay readable.
        label.set_hexpand(True)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        # Without this a long title asks for all the room it would need unwrapped, and the
        # card grows to fit it instead of ellipsizing. One character makes the label ask for
        # almost nothing, so the card's own width decides.
        label.set_max_width_chars(1)
    return label


def _split_row(leading: Gtk.Widget, trailing: Gtk.Widget) -> Gtk.Box:
    """A row with one widget pinned to each side, like the macOS card's split rows."""
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    row.append(leading)
    trailing.set_halign(Gtk.Align.END)
    row.append(trailing)
    return row
