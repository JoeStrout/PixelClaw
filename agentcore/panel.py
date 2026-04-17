from __future__ import annotations
from typing import Any

import raylib as rl


class Panel:
    """
    A named rectangular region of the window.

    Panels form a hierarchy: each panel owns a list of children whose positions
    are expressed relative to the parent's top-left corner.  The tree handles
    rendering (parent before children), mouse routing (hit-test, deepest child
    first), and keyboard routing (down the focus chain to the focused leaf).

    Subclass Panel and override the on_* hooks to add behaviour.  The handle_*
    methods are called by the parent (or by App at the root level) and should
    not normally be overridden.

    Coordinate convention
    ---------------------
    handle_* methods receive window-space coordinates.
    on_*     methods receive local coordinates (relative to this panel's origin).
    """

    def __init__(
        self,
        name: str,
        x: float = 0,
        y: float = 0,
        width: float = 0,
        height: float = 0,
    ) -> None:
        self.name = name
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.bg_color: Any | None = None   # filled before any other content; None = transparent
        self.parent: Panel | None = None
        self.children: list[Panel] = []
        self._focused_child: Panel | None = None

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    @property
    def abs_x(self) -> float:
        """X position in window space."""
        return self.x + (self.parent.abs_x if self.parent else 0.0)

    @property
    def abs_y(self) -> float:
        """Y position in window space."""
        return self.y + (self.parent.abs_y if self.parent else 0.0)

    def contains(self, wx: float, wy: float) -> bool:
        """Return True if the window-space point (wx, wy) falls inside this panel."""
        ax, ay = self.abs_x, self.abs_y
        return ax <= wx < ax + self.width and ay <= wy < ay + self.height

    # ------------------------------------------------------------------
    # Child management
    # ------------------------------------------------------------------

    def add(self, child: Panel) -> Panel:
        """Add a child panel and return it (for call-chaining)."""
        child.parent = self
        self.children.append(child)
        return child

    def remove(self, child: Panel) -> None:
        child.parent = None
        self.children.remove(child)
        if self._focused_child is child:
            self._focused_child = None

    def find(self, name: str) -> Panel | None:
        """Depth-first search for a descendant with the given name."""
        for child in self.children:
            if child.name == name:
                return child
            found = child.find(name)
            if found:
                return found
        return None

    # ------------------------------------------------------------------
    # Focus
    # ------------------------------------------------------------------

    @property
    def is_focused(self) -> bool:
        """True if keyboard events are currently routed to this panel (i.e. it is the focused leaf)."""
        if self._focused_child is not None:
            return False  # not the leaf
        node = self
        while node.parent is not None:
            if node.parent._focused_child is not node:
                return False
            node = node.parent
        return True

    def set_focus(self, child: Panel | None) -> None:
        """Direct keyboard focus to a child (or clear it with None)."""
        self._focused_child = child

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def draw_all(self) -> None:
        """Draw this panel then all children, recursively.  Called by App each frame."""
        self.draw()
        for child in self.children:
            child.draw_all()

    def draw(self) -> None:
        """Override to render this panel's content.  Called before children are drawn."""
        if self.bg_color is not None:
            rl.DrawRectangle(
                int(self.abs_x), int(self.abs_y),
                int(self.width), int(self.height),
                self.bg_color,
            )

    # ------------------------------------------------------------------
    # Mouse routing  (handle_* dispatches; on_* is the override point)
    # ------------------------------------------------------------------

    def handle_mouse_press(self, wx: float, wy: float, button: int) -> bool:
        """Route a mouse-button press to the deepest child that contains the point.
        Focus always follows the click regardless of whether the event is consumed.
        Returns True if consumed."""
        for child in reversed(self.children):  # later children are on top
            if child.contains(wx, wy):
                self._focused_child = child   # focus follows click unconditionally
                return child.handle_mouse_press(wx, wy, button)
        if self.contains(wx, wy):
            return self.on_mouse_press(wx - self.abs_x, wy - self.abs_y, button)
        return False

    def handle_mouse_release(self, wx: float, wy: float, button: int) -> None:
        """Route a mouse-button release to the deepest child that contains the point."""
        for child in reversed(self.children):
            if child.contains(wx, wy):
                child.handle_mouse_release(wx, wy, button)
                return
        if self.contains(wx, wy):
            self.on_mouse_release(wx - self.abs_x, wy - self.abs_y, button)

    def handle_mouse_move(self, wx: float, wy: float) -> None:
        """Propagate mouse-move to all children, then notify self."""
        for child in self.children:
            child.handle_mouse_move(wx, wy)
        self.on_mouse_move(wx - self.abs_x, wy - self.abs_y)

    def handle_mouse_wheel(self, wx: float, wy: float, delta: float) -> bool:
        """Route a scroll-wheel event to the deepest child under (wx, wy).  Returns True if consumed."""
        for child in reversed(self.children):
            if child.contains(wx, wy):
                return child.handle_mouse_wheel(wx, wy, delta)
        if self.contains(wx, wy):
            return self.on_mouse_wheel(wx - self.abs_x, wy - self.abs_y, delta)
        return False

    def on_mouse_press(self, x: float, y: float, button: int) -> bool:
        """Called with local coordinates when this panel is pressed.  Return True to consume."""
        return False

    def on_mouse_release(self, x: float, y: float, button: int) -> None:
        pass

    def on_mouse_move(self, x: float, y: float) -> None:
        pass

    def on_mouse_wheel(self, x: float, y: float, delta: float) -> bool:
        """Called when the scroll wheel moves over this panel.  Return True to consume."""
        return False

    # ------------------------------------------------------------------
    # Keyboard routing  (handle_* dispatches; on_* is the override point)
    # ------------------------------------------------------------------

    def handle_key_press(self, key: int) -> bool:
        """Route a key press down the focus chain.  Returns True if consumed."""
        if self._focused_child is not None:
            return self._focused_child.handle_key_press(key)
        return self.on_key_press(key)

    def handle_char(self, char: str) -> bool:
        """Route a character input down the focus chain.  Returns True if consumed."""
        if self._focused_child is not None:
            return self._focused_child.handle_char(char)
        return self.on_char(char)

    def on_key_press(self, key: int) -> bool:
        """Called when this panel has focus and a key is pressed.  Return True to consume."""
        return False

    def on_char(self, char: str) -> bool:
        """Called when this panel has focus and a printable character is typed.  Return True to consume."""
        return False

    # ------------------------------------------------------------------
    # Debug
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"Panel({self.name!r}, x={self.x}, y={self.y}, "
            f"w={self.width}, h={self.height}, children={len(self.children)})"
        )

    def dump(self, indent: int = 0) -> None:
        """Print the panel tree to stdout (for debugging)."""
        focus_marker = " *" if self.is_focused else ""
        print("  " * indent + repr(self) + focus_marker)
        for child in self.children:
            child.dump(indent + 1)
