from __future__ import annotations
from typing import Callable

import raylib as rl

from .panel import Panel
from .resources import bold_font

_ATLAS_CELL = 96
_ICON_SIZE  = 48
_TOP_PAD    = 0
_LABEL_GAP  = -2
_LABEL_SIZE = 12.0

_COLOR_NORMAL_TEXT   = (180, 180, 180, 255)
_COLOR_HOVER_TEXT    = (255, 255, 255, 255)
_COLOR_PRESSED_TEXT  = (150, 150, 150, 255)
_COLOR_DISABLED_TEXT = (90,  90,  90,  255)

_TINT_WHITE    = (255, 255, 255, 255)
_TINT_PRESSED  = (160, 160, 160, 255)
_TINT_DISABLED = (140, 140, 140, 255)


class ToolbarButton(Panel):
    """Icon-above-label toolbar button drawn from a texture atlas.

    The atlas has two rows: colored (colored_row) and grayscale (gray_row), with
    one column per button.  State determines which row and tint are used.
    """

    def __init__(
        self,
        name: str,
        label: str,
        atlas,
        col: int,
        colored_row: int = 0,
        gray_row: int = 1,
        on_click: Callable[[], None] | None = None,
        alt_label: str | None = None,
    ) -> None:
        super().__init__(name)
        self.label        = label
        self.alt_label    = alt_label
        self._atlas       = atlas
        self._col         = col
        self._colored_row = colored_row
        self._gray_row    = gray_row
        self.on_click     = on_click
        self.disabled     = False
        self.alt_held     = False   # set each frame by the owner panel
        self._hover       = False
        self._pressed     = False

    def on_mouse_move(self, lx: float, ly: float) -> None:
        over = 0.0 <= lx < self.width and 0.0 <= ly < self.height
        if self._pressed and not over:
            self._pressed = False
        self._hover = over

    def on_mouse_press(self, lx: float, ly: float, button: int) -> bool:
        if button == rl.MOUSE_BUTTON_LEFT and not self.disabled:
            self._pressed = True
            return True
        return False

    def on_mouse_release(self, lx: float, ly: float, button: int) -> None:
        if button == rl.MOUSE_BUTTON_LEFT:
            fire = self._pressed and not self.disabled
            self._pressed = False
            if fire and self.on_click:
                self.on_click()

    def draw(self) -> None:
        if self.disabled:
            row, tint, text_color = self._gray_row,    _TINT_DISABLED, _COLOR_DISABLED_TEXT
        elif self._pressed and self._hover:
            row, tint, text_color = self._colored_row, _TINT_PRESSED,  _COLOR_PRESSED_TEXT
        elif self._hover:
            row, tint, text_color = self._colored_row, _TINT_WHITE,    _COLOR_HOVER_TEXT
        else:
            row, tint, text_color = self._gray_row,    _TINT_WHITE,    _COLOR_NORMAL_TEXT

        ax = self.abs_x
        ay = self.abs_y
        icon_x = ax + (self.width - _ICON_SIZE) / 2
        icon_y = ay + _TOP_PAD

        src    = rl.ffi.new("Rectangle *", [
            float(self._col * _ATLAS_CELL), float(row * _ATLAS_CELL),
            float(_ATLAS_CELL),             float(_ATLAS_CELL),
        ])
        dst    = rl.ffi.new("Rectangle *", [icon_x, icon_y, float(_ICON_SIZE), float(_ICON_SIZE)])
        origin = rl.ffi.new("Vector2 *",   [0.0, 0.0])
        rl.DrawTexturePro(self._atlas, src[0], dst[0], origin[0], 0.0, tint)

        label = self.alt_label if (self.alt_held and self.alt_label) else self.label

        font  = bold_font()
        lw, _ = font.measure(label, _LABEL_SIZE)
        font.draw(
            label,
            ax + (self.width - lw) / 2,
            icon_y + _ICON_SIZE + _LABEL_GAP,
            _LABEL_SIZE,
            text_color,
        )
