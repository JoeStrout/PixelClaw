from __future__ import annotations
import sys
from pathlib import Path
from typing import Callable

import raylib as rl

_NS_ALT_MASK = 0x00080000  # NSAlternateKeyMask


def _alt_is_held() -> bool:
    if sys.platform == "darwin":
        try:
            from AppKit import NSEvent
            return bool(NSEvent.modifierFlags() & _NS_ALT_MASK)
        except Exception:
            pass
    return bool(rl.IsKeyDown(rl.KEY_LEFT_ALT)) or bool(rl.IsKeyDown(rl.KEY_RIGHT_ALT))

from agentcore.panel import Panel
from agentcore.resources import bold_font
from agentcore.toolbarbutton import ToolbarButton

_BUTTON_W    = 64
_BUTTON_GAP  = 4
_BUTTON_LEFT = 8

_SILVER       = (192, 192, 192, 255)
_TITLE_SIZE   = 48.0
_TITLE_MARGIN = 12.0

_ATLAS_PATH = Path(__file__).parent / "resources" / "toolbar_icons.png"
_ICON_PATH  = Path(__file__).parent / "resources" / "pixelclaw_icon.png"
_ICON_DRAW_SIZE = 48   # half of the 96px source


class HeaderPanel(Panel):
    """Header bar: Open/Save/Close toolbar on the left, app title on the right."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._atlas     = None
        self._icon      = None
        self._btn_open  = None
        self._btn_save  = None
        self._btn_close = None
        self._workspace = None

    def setup(
        self,
        workspace,
        on_open: Callable[[], None],
        on_save: Callable[[], None],
        on_close_doc: Callable[[], None],
    ) -> None:
        """Load GPU resources and create buttons. Call from on_start() after layout."""
        self._workspace = workspace
        self._atlas = rl.LoadTexture(str(_ATLAS_PATH).encode())
        rl.SetTextureFilter(self._atlas, rl.TEXTURE_FILTER_BILINEAR)
        self._icon = rl.LoadTexture(str(_ICON_PATH).encode())
        rl.SetTextureFilter(self._icon, rl.TEXTURE_FILTER_BILINEAR)

        self._btn_open  = ToolbarButton("btn_open",  "Open",  self._atlas, col=0, on_click=on_open)
        self._btn_save  = ToolbarButton("btn_save",  "Save",  self._atlas, col=1, on_click=on_save, alt_label="Save As")
        self._btn_close = ToolbarButton("btn_close", "Close", self._atlas, col=2, on_click=on_close_doc)

        for i, btn in enumerate((self._btn_open, self._btn_save, self._btn_close)):
            btn.x      = _BUTTON_LEFT + i * (_BUTTON_W + _BUTTON_GAP)
            btn.y      = 0.0
            btn.width  = _BUTTON_W
            btn.height = self.height
            self.add(btn)

    def unload(self) -> None:
        if self._atlas is not None:
            rl.UnloadTexture(self._atlas)
            self._atlas = None
        if self._icon is not None:
            rl.UnloadTexture(self._icon)
            self._icon = None

    def draw(self) -> None:
        super().draw()
        if self._btn_save is not None:
            has_doc = self._workspace.active_document is not None
            self._btn_save.disabled  = not has_doc
            self._btn_close.disabled = not has_doc
            self._btn_save.alt_held  = _alt_is_held()
        font = bold_font()
        text = "PixelClaw"
        tw, _ = font.measure(text, _TITLE_SIZE)
        text_x = self.abs_x + self.width - tw - _TITLE_MARGIN
        text_y = self.abs_y + _TITLE_MARGIN
        font.draw(text, text_x, text_y, _TITLE_SIZE, _SILVER)

        if self._icon is not None:
            icon_x = text_x - _ICON_DRAW_SIZE - 4
            icon_y = self.abs_y + (self.height - _ICON_DRAW_SIZE) / 2
            src    = rl.ffi.new("Rectangle *", [0.0, 0.0, 96.0, 96.0])
            dst    = rl.ffi.new("Rectangle *", [icon_x, icon_y,
                                                float(_ICON_DRAW_SIZE), float(_ICON_DRAW_SIZE)])
            origin = rl.ffi.new("Vector2 *",   [0.0, 0.0])
            rl.DrawTexturePro(self._icon, src[0], dst[0], origin[0], 0.0, (255, 255, 255, 255))
