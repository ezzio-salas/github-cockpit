"""The Personalize window.

A port of `macos/Sources/GitHubCockpit/CustomizationWindowController.swift`, and a sibling
of Claude Cockpit's. Not modal, so the card keeps refreshing behind it, and every change is
saved and applied immediately.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from cockpit_core.appearance import (  # noqa: E402
    MAXIMUM_TITLE_LENGTH,
    AppearanceStore,
    CockpitAppearance,
    HexColor,
    normalized_title,
)


class CustomizeWindow(Gtk.ApplicationWindow):
    """A title and three colors, the same four settings the macOS window offers."""

    def __init__(
        self,
        application: Gtk.Application,
        store: AppearanceStore,
        on_change: Callable[[CockpitAppearance], None],
    ) -> None:
        super().__init__(application=application, title="Personalize GitHub Cockpit")
        self._store = store
        self._on_change = on_change
        #: Set while the fields are being repopulated, so filling them in does not save.
        self._loading = False

        self.set_default_size(400, -1)
        self.set_resizable(False)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        for edge in ("top", "bottom", "start", "end"):
            getattr(content, f"set_margin_{edge}")(20)
        self.set_child(content)

        introduction = Gtk.Label(
            label="Give the widget its own title and colors, or close this window to keep "
            "the defaults. Changes apply as you make them. To come back here, right-click "
            "the card and choose Customize."
        )
        introduction.set_wrap(True)
        introduction.set_xalign(0)
        introduction.add_css_class("dim-label")
        content.append(introduction)

        grid = Gtk.Grid(column_spacing=14, row_spacing=12)
        content.append(grid)

        self._title_entry = Gtk.Entry()
        self._title_entry.set_max_length(MAXIMUM_TITLE_LENGTH)
        self._title_entry.set_placeholder_text(CockpitAppearance().title)
        self._title_entry.set_hexpand(True)
        self._title_entry.connect("changed", self._on_changed)
        _add_row(grid, 0, "Title", self._title_entry)

        self._accent = _color_button(self._on_changed)
        self._border = _color_button(self._on_changed)
        self._glow = _color_button(self._on_changed)
        _add_row(grid, 1, "Text color", self._accent)
        _add_row(grid, 2, "Border color", self._border)
        _add_row(grid, 3, "Glow color", self._glow)

        note = Gtk.Label(
            label="The stale marker stays amber whatever text color you pick, because "
            "there the color is the warning."
        )
        note.set_wrap(True)
        note.set_xalign(0)
        note.add_css_class("dim-label")
        content.append(note)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        buttons.set_halign(Gtk.Align.END)
        reset = Gtk.Button(label="Reset to Defaults")
        reset.connect("clicked", self._on_reset)
        done = Gtk.Button(label="Done")
        done.add_css_class("suggested-action")
        done.connect("clicked", lambda *_: self.close())
        buttons.append(reset)
        buttons.append(done)
        content.append(buttons)

        self._load(store.load())

    def _load(self, appearance: CockpitAppearance) -> None:
        self._loading = True
        try:
            # A title left at the default shows as the placeholder, so the field reads as
            # "nothing chosen" rather than as a value the person typed.
            default = CockpitAppearance().title
            self._title_entry.set_text("" if appearance.title == default else appearance.title)
            for button, color in (
                (self._accent, appearance.accent),
                (self._border, appearance.border),
                (self._glow, appearance.glow),
            ):
                rgba = Gdk.RGBA()
                rgba.parse(color.hex)
                button.set_rgba(rgba)
        finally:
            self._loading = False

    def _on_changed(self, *_args) -> None:
        if self._loading:
            return
        appearance = CockpitAppearance(
            title=normalized_title(self._title_entry.get_text()),
            accent=_hex(self._accent),
            border=_hex(self._border),
            glow=_hex(self._glow),
        )
        self._store.save(appearance)
        self._on_change(appearance)

    def _on_reset(self, *_args) -> None:
        self._store.reset()
        appearance = self._store.load()
        self._load(appearance)
        self._on_change(appearance)


def _add_row(grid: Gtk.Grid, row: int, name: str, control: Gtk.Widget) -> None:
    label = Gtk.Label(label=name)
    label.set_xalign(1)
    grid.attach(label, 0, row, 1, 1)
    grid.attach(control, 1, row, 1, 1)


def _color_button(on_changed) -> Gtk.ColorButton:
    button = Gtk.ColorButton()
    button.set_use_alpha(False)
    button.set_halign(Gtk.Align.START)
    button.connect("color-set", on_changed)
    return button


def _hex(button: Gtk.ColorButton) -> HexColor:
    rgba = button.get_rgba()
    return HexColor(rgba.red, rgba.green, rgba.blue)
