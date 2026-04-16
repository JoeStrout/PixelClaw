from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import raylib as rl

from .inputfield import InputField
from .ninepatch import NinePatch
from .panel import Panel
from .resources import default_font

_RESOURCES = Path(__file__).parent / "resources"

# Horizontal fraction of panel width used by each balloon
_BALLOON_WIDTH_FRACTION = 0.85
# Padding between balloon edge and text (all sides)
_TEXT_PAD = 10
# Additional padding on bottom
_BOTTOM_PAD = 14
# Extra vertical spacing between lines of wrapped text
_LINE_GAP = 2
# Vertical gap between successive balloons
_BALLOON_GAP = 8
# Pixels scrolled per wheel tick
_SCROLL_SPEED = 40
# Height of the input field at the bottom of the panel
_INPUT_HEIGHT = 36
# Vertical margin above/below the input field
_INPUT_MARGIN = 6


@dataclass
class ChatEntry:
    text: str
    source: str   # "agent" or "user"


class ChatPanel(Panel):
    """
    Scrollable chat transcript panel with an input field at the bottom.

    Each entry is rendered as text laid over a 9-slice speech balloon.
    Agent messages use speechBalloonLeft; user messages use speechBalloonRight.
    Scroll the transcript with the mouse wheel.
    """

    def __init__(self, name: str, x: float = 0, y: float = 0,
                 width: float = 0, height: float = 0,
                 on_message: Callable[[str], None] | None = None) -> None:
        super().__init__(name, x, y, width, height)
        self.on_message = on_message
        self.entries: list[ChatEntry] = []
        self.font_size: float = 14.0
        self._scroll_y: float = 0.0
        self._content_height: float = 0.0
        # Loaded lazily on first draw (requires an OpenGL context)
        self._balloon_left:  NinePatch | None = None
        self._balloon_right: NinePatch | None = None

        # Input field — position/size kept in sync with panel size
        self._input = InputField(
            "chat_input",
            on_submit=self._on_submit,
        )
        self._input.font_size = self.font_size
        self.add(self._input)
        self._layout_input()

    # ------------------------------------------------------------------
    # Size tracking — keep input field pinned to the bottom
    # ------------------------------------------------------------------

    def _input_y(self) -> float:
        return self.height - _INPUT_HEIGHT - _INPUT_MARGIN

    def _scroll_area_height(self) -> float:
        return self.height - _INPUT_HEIGHT - _INPUT_MARGIN * 2

    def _layout_input(self) -> None:
        self._input.x      = _INPUT_MARGIN
        self._input.y      = self._input_y()
        self._input.width  = self.width - _INPUT_MARGIN * 2
        self._input.height = _INPUT_HEIGHT

    # Override width/height setters to re-layout when the panel is resized
    @property  # type: ignore[override]
    def width(self) -> float:
        return self.__dict__.get("_width", 0.0)

    @width.setter
    def width(self, v: float) -> None:
        self.__dict__["_width"] = v
        if hasattr(self, "_input"):
            self._layout_input()

    @property  # type: ignore[override]
    def height(self) -> float:
        return self.__dict__.get("_height", 0.0)

    @height.setter
    def height(self, v: float) -> None:
        self.__dict__["_height"] = v
        if hasattr(self, "_input"):
            self._layout_input()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def add_entry(self, text: str, source: str) -> None:
        """Append a chat entry and scroll to the bottom."""
        self.entries.append(ChatEntry(text, source))
        self._recompute_content_height()
        self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        self._scroll_y = max(0.0, self._content_height - self._scroll_area_height())

    def _on_submit(self, text: str) -> None:
        if self.on_message:
            self.on_message(text)
        else:
            self.add_entry(text, "user")

    # ------------------------------------------------------------------
    # Lazy resource loading
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._balloon_left is None:
            self._balloon_left  = NinePatch(_RESOURCES / "speechBalloonLeft.png")
            self._balloon_right = NinePatch(_RESOURCES / "speechBalloonRight.png")

    def unload(self) -> None:
        if self._balloon_left:
            self._balloon_left.unload()
            self._balloon_left = None
        if self._balloon_right:
            self._balloon_right.unload()
            self._balloon_right = None

    # ------------------------------------------------------------------
    # Word wrap
    # ------------------------------------------------------------------

    def _wrap_text(self, text: str, max_width: float) -> list[str]:
        """Break *text* into lines that each fit within *max_width* logical pixels."""
        font = default_font()
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = word if not current else current + " " + word
            w, _ = font.measure(candidate, self.font_size)
            if w <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines if lines else [""]

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _balloon_width(self) -> float:
        return self.width * _BALLOON_WIDTH_FRACTION

    def _entry_height(self, entry: ChatEntry) -> float:
        """Total height (including vertical padding) of a single entry's balloon."""
        font = default_font()
        _, line_h = font.measure("Ag", self.font_size)
        text_w = self._balloon_width() - _TEXT_PAD * 2
        lines = self._wrap_text(entry.text, text_w)
        text_h = line_h * len(lines) + _LINE_GAP * (len(lines) - 1)
        return text_h + _TEXT_PAD * 2 + _BOTTOM_PAD

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self) -> None:
        super().draw()   # background fill
        self._ensure_loaded()
        self._recompute_content_height()

        font = default_font()
        _, line_h = font.measure("Ag", self.font_size)
        bw = self._balloon_width()
        ax, ay = self.abs_x, self.abs_y
        scroll_h = self._scroll_area_height()

        rl.BeginScissorMode(int(ax), int(ay), int(self.width), int(scroll_h))

        y = ay - self._scroll_y
        for entry in self.entries:
            bh = self._entry_height(entry)
            is_agent = entry.source == "agent"

            bx = ax if is_agent else ax + self.width - bw
            balloon = self._balloon_left if is_agent else self._balloon_right
            assert balloon is not None
            balloon.draw(bx, y, bw, bh)

            text_x = bx + _TEXT_PAD
            text_w = bw - _TEXT_PAD * 2
            ty = y + _TEXT_PAD
            for line in self._wrap_text(entry.text, text_w):
                font.draw(line, text_x, ty, self.font_size, rl.BLACK)
                ty += line_h + _LINE_GAP

            y += bh + _BALLOON_GAP

        rl.EndScissorMode()

    def _recompute_content_height(self) -> None:
        total = sum(self._entry_height(e) + _BALLOON_GAP for e in self.entries)
        self._content_height = max(total, 0.0)

    # ------------------------------------------------------------------
    # Scroll input — only when mouse is over the transcript area
    # ------------------------------------------------------------------

    def on_mouse_wheel(self, x: float, y: float, delta: float) -> bool:
        if y >= self._input_y():
            return False   # over input field; don't scroll transcript
        max_scroll = max(0.0, self._content_height - self._scroll_area_height())
        direction = 1 if delta < 0 else -1
        self._scroll_y = max(0.0, min(self._scroll_y + direction * _SCROLL_SPEED, max_scroll))
        return True
