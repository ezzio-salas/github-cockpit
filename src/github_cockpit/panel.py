"""The window the card lives in: an overlay that floats above everything and never takes focus."""

from __future__ import annotations

import logging
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, Gtk  # noqa: E402

from cockpit_core.appearance import AppearanceStore, CockpitAppearance

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

        self._menu = Gtk.PopoverMenu.new_from_model(self._menu_model())
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

    def _on_secondary_press(self, _gesture: Gtk.GestureClick, _n: int, x: float, y: float) -> None:
        self._menu.set_pointing_to(Gdk.Rectangle(x=int(x), y=int(y), width=1, height=1))
        self._menu.popup()

    def _menu_model(self) -> Gio.Menu:
        menu = Gio.Menu()
        menu.append("Refresh", "app.refresh")
        menu.append("Open GitHub Pull Requests", "app.open-github")
        menu.append("Quit GitHub Cockpit", "app.quit")
        return menu
