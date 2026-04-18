from __future__ import annotations

from typing import Callable

import raylib as rl

from .panel import Panel
from .resources import default_font

_PAD        = 6      # pixels between border and text
_BORDER     = 1      # border thickness
_CURSOR_W   = 2      # cursor bar width
_BLINK_RATE = 0.53   # seconds per half-cycle

_COLOR_BG             = (255, 255, 255, 255)
_COLOR_BORDER         = (160, 160, 160, 255)
_COLOR_BORDER_FOCUSED = (80,  120, 200, 255)
_COLOR_PROMPT         = (180, 180, 180, 255)
_COLOR_TEXT           = (20,   20,  20, 255)
_COLOR_SELECTION      = (180, 210, 255, 200)
_COLOR_CURSOR         = (40,   40,  40, 255)


def _ctrl() -> bool:
    return rl.IsKeyDown(rl.KEY_LEFT_CONTROL) or rl.IsKeyDown(rl.KEY_RIGHT_CONTROL)

def _shift() -> bool:
    return rl.IsKeyDown(rl.KEY_LEFT_SHIFT) or rl.IsKeyDown(rl.KEY_RIGHT_SHIFT)

def _alt() -> bool:
    return rl.IsKeyDown(rl.KEY_LEFT_ALT) or rl.IsKeyDown(rl.KEY_RIGHT_ALT)


class InputField(Panel):
    """
    Single-line text input with selection, clipboard, and horizontal scrolling.

    Visual states
    -------------
    Unfocused + empty : white bg, gray border, light-gray prompt text
    Unfocused + text  : white bg, gray border, text (no cursor)
    Focused           : white bg, blue border, text, blinking cursor, selection highlight

    Key bindings
    ------------
    Left / Right               move cursor one character
    Alt+Left / Right           move cursor one word  (Ctrl also accepted)
    Shift+any-movement         extend selection
    Home / End  or  Up / Down  jump to start / end of field
    Backspace / Delete         delete selection or adjacent character (auto-repeat)
    Alt+Backspace              delete word to the left
    Alt+Delete                 delete word to the right
    Ctrl+A                     select all
    Ctrl+C                     copy selection
    Ctrl+X                     cut selection
    Ctrl+V                     paste clipboard
    Enter / KP_Enter           call on_submit(text) and clear the field
    Escape                     clear selection
    """

    def __init__(
        self,
        name: str,
        x: float = 0, y: float = 0,
        width: float = 0, height: float = 0,
        prompt: str = "Click to type",
        on_submit: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(name, x, y, width, height)
        self.prompt    = prompt
        self.on_submit = on_submit
        self.font_size: float = 14.0

        self.text                          = ""
        self.cursor_pos                    = 0
        self.selection_anchor: int | None  = None

        self._scroll_x = 0.0
        self._dragging = False

    # ------------------------------------------------------------------
    # Selection helpers
    # ------------------------------------------------------------------

    def _sel_range(self) -> tuple[int, int] | None:
        if self.selection_anchor is None or self.selection_anchor == self.cursor_pos:
            return None
        lo = min(self.selection_anchor, self.cursor_pos)
        hi = max(self.selection_anchor, self.cursor_pos)
        return lo, hi

    def _selected_text(self) -> str:
        r = self._sel_range()
        return self.text[r[0]:r[1]] if r else ""

    def _delete_selection(self) -> bool:
        r = self._sel_range()
        if not r:
            return False
        lo, hi = r
        self.text = self.text[:lo] + self.text[hi:]
        self.cursor_pos = lo
        self.selection_anchor = None
        return True

    def _clear_selection(self) -> None:
        self.selection_anchor = None

    def _start_selection_from_cursor(self) -> None:
        if self.selection_anchor is None:
            self.selection_anchor = self.cursor_pos

    # ------------------------------------------------------------------
    # Cursor / scroll helpers
    # ------------------------------------------------------------------

    def _char_x(self, pos: int) -> float:
        w, _ = default_font().measure(self.text[:pos], self.font_size)
        return w

    def _x_to_char(self, local_x: float) -> int:
        font = default_font()
        best_i, best_dist = 0, abs(local_x)
        for i in range(1, len(self.text) + 1):
            w, _ = font.measure(self.text[:i], self.font_size)
            dist = abs(local_x - w)
            if dist < best_dist:
                best_dist, best_i = dist, i
            elif w > local_x + 20:
                break
        return best_i

    def _word_left(self, pos: int) -> int:
        p = pos - 1
        while p > 0 and self.text[p - 1] != ' ':
            p -= 1
        return max(0, p)

    def _word_right(self, pos: int) -> int:
        p = pos
        while p < len(self.text) and self.text[p] != ' ':
            p += 1
        while p < len(self.text) and self.text[p] == ' ':
            p += 1
        return p

    def _clamp_scroll(self) -> None:
        text_area_w = self.width - _PAD * 2 - _BORDER * 2
        cx = self._char_x(self.cursor_pos)
        if cx - self._scroll_x > text_area_w:
            self._scroll_x = cx - text_area_w
        if cx - self._scroll_x < 0:
            self._scroll_x = cx
        self._scroll_x = max(0.0, self._scroll_x)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self) -> None:
        ax, ay  = int(self.abs_x), int(self.abs_y)
        w, h    = int(self.width), int(self.height)
        font    = default_font()
        focused = self.is_focused

        # Background + border
        rl.DrawRectangle(ax, ay, w, h, _COLOR_BG)
        border_color = _COLOR_BORDER_FOCUSED if focused else _COLOR_BORDER
        rl.DrawRectangleLinesEx(
            rl.ffi.new("Rectangle *", [ax, ay, w, h])[0],
            _BORDER, border_color,
        )

        inner_x = ax + _BORDER + _PAD
        inner_w = w - (_BORDER + _PAD) * 2
        inner_y = ay + _BORDER
        inner_h = h - _BORDER * 2
        rl.BeginScissorMode(inner_x, inner_y, inner_w, inner_h)

        # Vertically centre text within the field
        text_y = ay + (h - self.font_size) / 2

        if not self.text and not focused:
            font.draw(self.prompt, inner_x, text_y, self.font_size, _COLOR_PROMPT)
        else:
            text_origin = inner_x - self._scroll_x

            # Selection highlight — same height as the text, not the full inner box
            sel = self._sel_range()
            win_focused = rl.IsWindowFocused()
            if sel:
                lo, hi = sel
                sx = text_origin + self._char_x(lo)
                sw = self._char_x(hi) - self._char_x(lo)
                if win_focused:
                    rl.DrawRectangle(
                        int(sx), int(text_y),
                        int(sw), int(self.font_size),
                        _COLOR_SELECTION,
                    )
                else:
                    rl.DrawRectangleLinesEx(
                        rl.ffi.new("Rectangle *", [sx, text_y, sw, self.font_size])[0],
                        _BORDER, _COLOR_SELECTION,
                    )

            font.draw(self.text, text_origin, text_y, self.font_size, _COLOR_TEXT)

            # Blinking cursor — only when focused, window active, and no active selection
            if focused and win_focused and not sel and int(rl.GetTime() / _BLINK_RATE) % 2 == 0:
                cx = int(text_origin + self._char_x(self.cursor_pos))
                rl.DrawRectangle(cx, int(text_y), _CURSOR_W, int(self.font_size), _COLOR_CURSOR)

        rl.EndScissorMode()

    # ------------------------------------------------------------------
    # Mouse input
    # ------------------------------------------------------------------

    def on_mouse_press(self, x: float, y: float, button: int) -> bool:
        if button != rl.MOUSE_BUTTON_LEFT:
            return False
        pos = self._x_to_char(x - _PAD - _BORDER + self._scroll_x)
        if _shift() and self.selection_anchor is None:
            self.selection_anchor = self.cursor_pos
        else:
            self.selection_anchor = None
        self.cursor_pos = pos
        self._dragging  = True
        return True

    def on_mouse_move(self, x: float, y: float) -> None:
        if self._dragging and rl.IsMouseButtonDown(rl.MOUSE_BUTTON_LEFT):
            new_pos = self._x_to_char(x - _PAD - _BORDER + self._scroll_x)
            if new_pos != self.cursor_pos:
                if self.selection_anchor is None:
                    self.selection_anchor = self.cursor_pos
                self.cursor_pos = new_pos

    def on_mouse_release(self, x: float, y: float, button: int) -> None:
        if button == rl.MOUSE_BUTTON_LEFT:
            self._dragging = False
            if self.selection_anchor == self.cursor_pos:
                self.selection_anchor = None

    # ------------------------------------------------------------------
    # Keyboard input
    # ------------------------------------------------------------------

    def on_key_press(self, key: int) -> bool:
        ctrl  = _ctrl()
        shift = _shift()
        word  = _alt() or ctrl   # word-movement modifier: Alt (primary) or Ctrl

        # --- Ctrl-only shortcuts (not shared with word movement) ---
        if ctrl and not _alt():
            if key == rl.KEY_A:
                self.selection_anchor = 0
                self.cursor_pos = len(self.text)
                return True
            if key == rl.KEY_C:
                t = self._selected_text()
                if t:
                    rl.SetClipboardText(t.encode())
                return True
            if key == rl.KEY_X:
                t = self._selected_text()
                if t:
                    rl.SetClipboardText(t.encode())
                    self._delete_selection()
                return True
            if key == rl.KEY_V:
                raw  = rl.GetClipboardText()
                clip = rl.ffi.string(raw).decode() if raw else ""
                if clip:
                    self._delete_selection()
                    self.text = self.text[:self.cursor_pos] + clip + self.text[self.cursor_pos:]
                    self.cursor_pos += len(clip)
                    self._clear_selection()
                return True

        # --- Word movement (Alt or Ctrl + Left/Right) ---
        if word and key == rl.KEY_LEFT:
            if shift: self._start_selection_from_cursor()
            else:     self._clear_selection()
            self.cursor_pos = self._word_left(self.cursor_pos)
            self._clamp_scroll()
            return True

        if word and key == rl.KEY_RIGHT:
            if shift: self._start_selection_from_cursor()
            else:     self._clear_selection()
            self.cursor_pos = self._word_right(self.cursor_pos)
            self._clamp_scroll()
            return True

        # --- Character movement ---
        if key == rl.KEY_LEFT:
            if shift: self._start_selection_from_cursor()
            else:     self._clear_selection()
            if self.cursor_pos > 0:
                self.cursor_pos -= 1
            self._clamp_scroll()
            return True

        if key == rl.KEY_RIGHT:
            if shift: self._start_selection_from_cursor()
            else:     self._clear_selection()
            if self.cursor_pos < len(self.text):
                self.cursor_pos += 1
            self._clamp_scroll()
            return True

        # --- Jump to start / end (Home, End, Up, Down) ---
        if key in (rl.KEY_HOME, rl.KEY_UP):
            if shift: self._start_selection_from_cursor()
            else:     self._clear_selection()
            self.cursor_pos = 0
            self._clamp_scroll()
            return True

        if key in (rl.KEY_END, rl.KEY_DOWN):
            if shift: self._start_selection_from_cursor()
            else:     self._clear_selection()
            self.cursor_pos = len(self.text)
            self._clamp_scroll()
            return True

        if key == rl.KEY_ESCAPE:
            self._clear_selection()
            return True

        # --- Deletion (auto-repeat via IsKeyPressedRepeat) ---
        if rl.IsKeyPressedRepeat(rl.KEY_BACKSPACE) or key == rl.KEY_BACKSPACE:
            if not self._delete_selection():
                if _alt() and self.cursor_pos > 0:
                    target = self._word_left(self.cursor_pos)
                    self.text = self.text[:target] + self.text[self.cursor_pos:]
                    self.cursor_pos = target
                elif self.cursor_pos > 0:
                    self.text = self.text[:self.cursor_pos - 1] + self.text[self.cursor_pos:]
                    self.cursor_pos -= 1
            self._clamp_scroll()
            return True

        if rl.IsKeyPressedRepeat(rl.KEY_DELETE) or key == rl.KEY_DELETE:
            if not self._delete_selection():
                if _alt() and self.cursor_pos < len(self.text):
                    target = self._word_right(self.cursor_pos)
                    self.text = self.text[:self.cursor_pos] + self.text[target:]
                elif self.cursor_pos < len(self.text):
                    self.text = self.text[:self.cursor_pos] + self.text[self.cursor_pos + 1:]
            self._clamp_scroll()
            return True

        # --- Submit ---
        if key in (rl.KEY_ENTER, rl.KEY_KP_ENTER):
            if self.on_submit and self.text.strip():
                self.on_submit(self.text)
                self.text          = ""
                self.cursor_pos    = 0
                self.selection_anchor = None
                self._scroll_x     = 0.0
            return True

        return False

    def on_char(self, char: str) -> bool:
        self._delete_selection()
        self.selection_anchor = None
        self.text = self.text[:self.cursor_pos] + char + self.text[self.cursor_pos:]
        self.cursor_pos += 1
        self._clamp_scroll()
        return True

    def insert_text(self, s: str) -> None:
        """Insert *s* at the current cursor position, replacing any selection."""
        self._delete_selection()
        self.selection_anchor = None
        self.text = self.text[:self.cursor_pos] + s + self.text[self.cursor_pos:]
        self.cursor_pos += len(s)
        self._clamp_scroll()
