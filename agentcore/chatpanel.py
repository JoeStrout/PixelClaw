from __future__ import annotations

import queue
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import raylib as rl

from .inputfield import InputField
from .mdrender import parse, wrap_runs, draw_runs
from .ninepatch import NinePatch
from .panel import Panel
from .resources import default_font, style_font_map

try:
    from . import stt as _stt
    _STT_AVAILABLE = True
except Exception:
    _stt = None          # type: ignore[assignment]
    _STT_AVAILABLE = False

from . import speech as _speech

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
# Mic button dimensions (icon is 24×48, drawn at half scale → 12×24 logical px)
_MIC_BTN_W    = 28
_MIC_BTN_GAP  = 4
_MIC_ICON_W   = 12
_MIC_ICON_H   = 24
# Long-press threshold in seconds
_LONG_PRESS_S = 0.3
# Mic button tints by STT state
_TINT_IDLE         = (160, 160, 160, 255)
_TINT_RECORDING    = (220,  60,  60, 255)
_TINT_TRANSCRIBING = (200, 150,  50, 255)
# Seconds before the thinking indicator appears
_THINKING_DELAY = 5.0
# Vertical space reserved for the thinking dots
_THINKING_HEIGHT = 24


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

    Speech-to-text (F5 or mic button click):
      Brief press  → record until 1 s of silence, then transcribe.
      Long press   → record while held; release immediately transcribes.
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
        self._mic_texture = None    # loaded lazily

        self.thinking: bool = False
        self._thinking_start: float = 0.0
        self._thinking_shown: bool = False  # tracks first-visible frame for auto-scroll

        # STT state
        self._f2_press_time: float | None = None    # monotonic time of F2 press
        self._stt_queue: queue.SimpleQueue[str | None] = queue.SimpleQueue()

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
        self._input.width  = self.width - _INPUT_MARGIN * 2 - _MIC_BTN_W - _MIC_BTN_GAP
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
    # Speech-to-text  (called by PixelClawApp._process_input for F2,
    # and by on_mouse_press for mic button clicks)
    # ------------------------------------------------------------------

    def on_mic_press(self) -> None:
        """Call when F5 is pressed."""
        if not _STT_AVAILABLE:
            return
        if _stt.state() != "idle":
            return
        print("[stt] F5 down — recording started")
        _speech.stop()
        self._f2_press_time = time.monotonic()
        _stt.start_recording()

    def on_mic_release(self) -> None:
        """Call when F5 is released; chooses VAD vs immediate mode."""
        if not _STT_AVAILABLE:
            return
        if _stt.state() != "recording" or self._f2_press_time is None:
            return
        held = time.monotonic() - self._f2_press_time
        self._f2_press_time = None
        if held >= _LONG_PRESS_S:
            print(f"[stt] F2 up after {held:.2f}s — push-to-talk mode")
            _stt.commit_immediate(self._stt_queue.put)
        else:
            print(f"[stt] F2 up after {held:.2f}s — VAD mode")
            _stt.commit_vad(self._stt_queue.put)

    def _mic_btn_rect(self) -> tuple[float, float, float, float]:
        """Local-space (x, y, w, h) of the mic button."""
        x = self.width - _INPUT_MARGIN - _MIC_BTN_W
        y = self._input_y() - 2
        return x, y, _MIC_BTN_W, _INPUT_HEIGHT

    def on_mouse_press(self, lx: float, ly: float, button: int) -> bool:
        if button == rl.MOUSE_BUTTON_LEFT:
            bx, by, bw, bh = self._mic_btn_rect()
            if bx <= lx < bx + bw and by <= ly < by + bh:
                if _STT_AVAILABLE:
                    if _stt.state() == "idle":
                        _speech.stop()
                        _stt.start_recording()
                        _stt.commit_vad(self._stt_queue.put)
                    else:
                        _stt.cancel()
                return True
        return False

    # ------------------------------------------------------------------
    # Lazy resource loading
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._balloon_left is None:
            self._balloon_left  = NinePatch(_RESOURCES / "speechBalloonLeft.png")
            self._balloon_right = NinePatch(_RESOURCES / "speechBalloonRight.png")
        if self._mic_texture is None:
            mic_path = str(_RESOURCES / "MicIcon.png").encode()
            self._mic_texture = rl.LoadTexture(mic_path)

    def unload(self) -> None:
        if self._balloon_left:
            self._balloon_left.unload()
            self._balloon_left = None
        if self._balloon_right:
            self._balloon_right.unload()
            self._balloon_right = None
        if self._mic_texture is not None:
            rl.UnloadTexture(self._mic_texture)
            self._mic_texture = None

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _balloon_width(self) -> float:
        return self.width * _BALLOON_WIDTH_FRACTION

    def _entry_height(self, entry: ChatEntry) -> float:
        """Total height (including vertical padding) of a single entry's balloon."""
        _, line_h = default_font().measure("Ag", self.font_size)
        text_w = self._balloon_width() - _TEXT_PAD * 2
        lines = wrap_runs(parse(entry.text), text_w, self.font_size, style_font_map())
        text_h = line_h * len(lines) + _LINE_GAP * (len(lines) - 1)
        return text_h + _TEXT_PAD * 2 + _BOTTOM_PAD

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self) -> None:
        super().draw()   # background fill
        self._ensure_loaded()
        self._recompute_content_height()

        # Drain STT results delivered from background thread
        while not self._stt_queue.empty():
            text = self._stt_queue.get_nowait()
            if text:
                self._input.insert_text(text)
            else:
                print("[stt] transcription returned nothing")

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
            fmap = style_font_map()
            for line_runs in wrap_runs(parse(entry.text), text_w, self.font_size, fmap):
                draw_runs(line_runs, text_x, ty, self.font_size, rl.BLACK, fmap)
                ty += line_h + _LINE_GAP

            y += bh + _BALLOON_GAP

        # Thinking indicator — three pulsing dots below the last balloon
        if self.thinking and rl.GetTime() - self._thinking_start >= _THINKING_DELAY:
            if not self._thinking_shown:
                self._thinking_shown = True
                self._scroll_to_bottom()
            dot_r = 4
            dot_cx = ax + _TEXT_PAD + dot_r
            dot_cy = int(y + dot_r + 4)
            t = rl.GetTime()
            active = int(t / 0.4) % 3
            for i in range(3):
                color = (220, 220, 220, 255) if i == active else (140, 140, 140, 110)
                rl.DrawCircle(int(dot_cx + i * (dot_r * 2 + 6)), dot_cy, dot_r, color)
        else:
            self._thinking_shown = False

        rl.EndScissorMode()

        # Mic button (drawn outside scissor so it's always visible)
        if self._mic_texture is not None and _STT_AVAILABLE:
            stt_state = _stt.state()
            if stt_state == "recording":
                tint = _TINT_RECORDING
                # Pulse alpha to signal active recording
                pulse = int(180 + 75 * abs((rl.GetTime() % 1.0) * 2 - 1))
                tint = (_TINT_RECORDING[0], _TINT_RECORDING[1], _TINT_RECORDING[2], pulse)
            elif stt_state == "transcribing":
                tint = _TINT_TRANSCRIBING
            else:
                tint = _TINT_IDLE
            bx, by, bw, bh = self._mic_btn_rect()
            icon_x = int(self.abs_x + bx + (bw - _MIC_ICON_W) / 2)
            icon_y = int(self.abs_y + by + (bh - _MIC_ICON_H) / 2)
            src = rl.ffi.new("Rectangle *", [0.0, 0.0, 24.0, 48.0])
            dst = rl.ffi.new("Rectangle *",
                             [float(icon_x), float(icon_y),
                              float(_MIC_ICON_W), float(_MIC_ICON_H)])
            origin = rl.ffi.new("Vector2 *", [0.0, 0.0])
            rl.DrawTexturePro(self._mic_texture, src[0], dst[0], origin[0], 0.0, tint)
            label_size = 9.0
            font = default_font()
            lw, _ = font.measure("F5", label_size)
            label_x = self.abs_x + bx + (bw - lw) / 2
            label_y = icon_y + _MIC_ICON_H + 1
            font.draw("F5", label_x, label_y, label_size, (120, 120, 120, 200))

    def _recompute_content_height(self) -> None:
        total = sum(self._entry_height(e) + _BALLOON_GAP for e in self.entries)
        if self.thinking and rl.GetTime() - self._thinking_start >= _THINKING_DELAY:
            total += _THINKING_HEIGHT
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
