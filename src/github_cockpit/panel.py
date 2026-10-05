"""The window the card lives in: an overlay that floats above everything and never takes focus."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from cockpit_core.appearance import AppearanceStore, CockpitAppearance
from cockpit_core.comments import PullRequestComment
from cockpit_core.pull_request import PullRequest

from . import theme
from .view import CockpitSnapshot, CockpitView

log = logging.getLogger(__name__)

#: The compositor sees this name; Hyprland's `layerrule` uses it to blur behind the card.
NAMESPACE = "github-cockpit"

try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell as LayerShell

    HAS_LAYER_SHELL = True
except (ImportError, ValueError):  # the library or its typelib is not installed
    LayerShell = None
    HAS_LAYER_SHELL = False


class CockpitPanel(Gtk.ApplicationWindow):
    """A frameless overlay pinned near the top-right corner.

    With gtk4-layer-shell it is a layer surface: above full-screen windows, on every
    workspace, and never focusable. Without it the window is an ordinary toplevel and the
    compositor has to be told to float and pin it; see the README.
    """

    def __init__(self, application: Gtk.Application, store: AppearanceStore) -> None:
        super().__init__(application=application)
        self._store = store
        self._css = Gtk.CssProvider()
        self._top, self._right = store.load_placement()
        self._drag_origin: tuple[int, int] | None = None
        #: Called after the card has been dragged to a new place.
        self.on_moved: Callable[[], None] | None = None

        self.set_decorated(False)
        self.set_resizable(False)
        self.add_css_class("cockpit")
        self.set_title("GitHub Cockpit")

        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, self._css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

        self.view = CockpitView()
        self.set_child(self.view)
        self._setup_layer_shell()
        self._setup_gestures()

    # MARK: - Placement

    def _setup_layer_shell(self) -> None:
        if not HAS_LAYER_SHELL:
            log.warning(
                "gtk4-layer-shell is not installed; the card is an ordinary window. "
                "Install it, or add the compositor rules from the README."
            )
            return
        LayerShell.init_for_window(self)
        LayerShell.set_namespace(self, NAMESPACE)
        # Overlay keeps the card above full-screen windows, as the macOS panel's floating
        # level does; NONE means it never takes the keyboard, so typing is never interrupted.
        LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
        LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.NONE)
        LayerShell.set_anchor(self, LayerShell.Edge.TOP, True)
        LayerShell.set_anchor(self, LayerShell.Edge.RIGHT, True)
        self._apply_margins()

        # Initialising can still fail silently when the library was linked after
        # libwayland, which is what happens when python is run without the LD_PRELOAD
        # run.sh sets. Say so plainly rather than leaving only GTK's warning.
        if not LayerShell.is_layer_window(self):
            log.warning(
                "gtk4-layer-shell is installed but did not take effect, so the card is an "
                "ordinary window. Start it with run.sh, which sets the LD_PRELOAD it needs."
            )

    def _apply_margins(self) -> None:
        if not HAS_LAYER_SHELL:
            return
        LayerShell.set_margin(self, LayerShell.Edge.TOP, self._top)
        LayerShell.set_margin(self, LayerShell.Edge.RIGHT, self._right)

    def _move_by(self, dx: float, dy: float) -> None:
        """Moves the card, keeping it on screen.

        Anchored to the top-right, a drag to the right shrinks the right margin and a drag
        downwards grows the top one.
        """
        if self._drag_origin is None:
            return
        start_top, start_right = self._drag_origin
        self._top = max(0, int(start_top + dy))
        self._right = max(0, int(start_right - dx))
        self._apply_margins()

    def set_on_hover_change(self, callback: Callable[[PullRequest | None], None]) -> None:
        """Called with the pull request under the pointer whenever it changes."""
        self.view.on_hover_change = callback

    @property
    def placement(self) -> tuple[int, int]:
        """The window's distance from the top and right edges of the screen, in pixels."""
        return self._top, self._right

    def anchor_y(self, comment: PullRequestComment) -> float:
        """The height on this window a bubble about `comment` points at: the middle of its row,
        or the card's header when the row is not shown."""
        row = self.view.row_for(comment.number, comment.repo)
        if row is not None:
            found, bounds = row.compute_bounds(self)
            if found:
                return bounds.get_y() + bounds.get_height() / 2
        return theme.GLOW_MARGIN + theme.PADDING + theme.HEADER_HEIGHT / 2

    def screen_width(self) -> int:
        """The width of the monitor the card is on, or 0 when it is not known yet."""
        surface = self.get_surface()
        display = self.get_display()
        if surface is None or display is None:
            return 0
        monitor = display.get_monitor_at_surface(surface)
        return monitor.get_geometry().width if monitor is not None else 0

    # MARK: - Appearance

    def apply(self, appearance: CockpitAppearance) -> None:
        self._css.load_from_string(theme.stylesheet(appearance))
        self.view.apply(appearance)

    def render(self, snapshot: CockpitSnapshot, now: datetime) -> None:
        self.view.render(snapshot, now)

    # MARK: - Mouse

    def _setup_gestures(self) -> None:
        # Capture phase: the card sees the pointer before the rows do, so once a press turns
        # into a drag it can claim the sequence and the row underneath never fires.
        drag = Gtk.GestureDrag()
        drag.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.view.add_controller(drag)

        secondary = Gtk.GestureClick()
        secondary.set_button(Gdk.BUTTON_SECONDARY)
        secondary.connect("pressed", self._on_secondary_press)
        self.view.add_controller(secondary)

        self._menu = Gtk.PopoverMenu.new_from_model(self._menu_model(None))
        self._menu.set_parent(self.view)
        self._menu.set_has_arrow(False)

    def _on_drag_begin(self, _gesture: Gtk.GestureDrag, _x: float, _y: float) -> None:
        self._drag_origin = (self._top, self._right)

    def _on_drag_update(self, gesture: Gtk.GestureDrag, dx: float, dy: float) -> None:
        if max(abs(dx), abs(dy)) < theme.DRAG_THRESHOLD:
            return
        # Claiming here is what distinguishes a move from a click on a pull request.
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self._move_by(dx, dy)

    def _on_drag_end(self, gesture: Gtk.GestureDrag, dx: float, dy: float) -> None:
        if self._drag_origin is None:
            return
        self._drag_origin = None
        if max(abs(dx), abs(dy)) >= theme.DRAG_THRESHOLD:
            self._move_by(dx, dy)
            self._store.save_placement(self._top, self._right)
            if self.on_moved is not None:
                self.on_moved()

    def _on_secondary_press(self, _gesture: Gtk.GestureClick, _n: int, x: float, y: float) -> None:
        self._menu.set_menu_model(self._menu_model(self.view.pull_at(x, y)))
        self._menu.set_pointing_to(Gdk.Rectangle(x=int(x), y=int(y), width=1, height=1))
        self._menu.popup()

    def _menu_model(self, pull: PullRequest | None) -> Gio.Menu:
        """The card's menu, with items about `pull` above it when a row was right-clicked."""
        menu = Gio.Menu()
        if pull is not None:
            row = Gio.Menu()
            items = (("Open Pull Request", "app.open-pr"), ("Copy Link", "app.copy-link"))
            for label, action in items:
                item = Gio.MenuItem.new(label, None)
                item.set_action_and_target_value(action, GLib.Variant.new_string(pull.url))
                row.append_item(item)
            menu.append_section(None, row)

        card = Gio.Menu()
        card.append("Refresh", "app.refresh")
        card.append("Open GitHub Pull Requests", "app.open-github")
        card.append("Customize…", "app.customize")
        card.append("Quit GitHub Cockpit", "app.quit")
        menu.append_section(None, card)
        return menu
