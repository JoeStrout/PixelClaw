from __future__ import annotations

from pathlib import Path

import raylib as rl

from agentcore.context import Context
from agentcore.panel import Panel
from agentcore.resources import default_font

from .document import ImageDocument
from . import textures

_HINT_COLOR = (100, 100, 100, 255)
_HINT_SIZE  = 16.0
_BG_PATTERN = Path(__file__).parent / "resources" / "backgroundPattern.png"


class MainPanel(Panel):
    """
    Central panel that displays the active document scaled to fit.
    """

    def __init__(
        self,
        name: str,
        context: Context,
        x: float = 0, y: float = 0,
        width: float = 0, height: float = 0,
    ) -> None:
        super().__init__(name, x, y, width, height)
        self._context = context
        self._bg_tex = None   # loaded lazily after InitWindow

    def _ensure_bg(self) -> None:
        if self._bg_tex is not None:
            return
        self._bg_tex = rl.LoadTexture(str(_BG_PATTERN).encode())
        rl.SetTextureWrap(self._bg_tex, rl.TEXTURE_WRAP_REPEAT)

    def unload(self) -> None:
        if self._bg_tex is not None:
            rl.UnloadTexture(self._bg_tex)
            self._bg_tex = None

    def draw(self) -> None:
        super().draw()

        doc = self._context.active_document
        if not isinstance(doc, ImageDocument):
            self._draw_hint("Drop an image file to get started")
            return

        tex = textures.get_display_texture(doc)
        if tex is None:
            self._draw_hint("(no image data)")
            return

        # Scale to fit while preserving aspect ratio
        scale  = min(self.width / tex.width, self.height / tex.height)
        draw_w = tex.width  * scale
        draw_h = tex.height * scale
        draw_x = self.abs_x + (self.width  - draw_w) / 2
        draw_y = self.abs_y + (self.height - draw_h) / 2

        # Tiled checkerboard behind the image
        self._ensure_bg()
        if self._bg_tex.id != 0:
            bg_src  = rl.ffi.new("Rectangle *", [0.0, 0.0, draw_w, draw_h])
            bg_dest = rl.ffi.new("Rectangle *", [draw_x, draw_y, draw_w, draw_h])
            origin  = rl.ffi.new("Vector2 *",   [0.0, 0.0])
            rl.DrawTexturePro(self._bg_tex, bg_src[0], bg_dest[0], origin[0], 0.0, rl.WHITE)

        src  = rl.ffi.new("Rectangle *", [0.0, 0.0, float(tex.width), float(tex.height)])
        dest = rl.ffi.new("Rectangle *", [draw_x, draw_y, draw_w, draw_h])
        origin = rl.ffi.new("Vector2 *", [0.0, 0.0])
        rl.DrawTexturePro(tex, src[0], dest[0], origin[0], 0.0, rl.WHITE)

    def _draw_hint(self, text: str) -> None:
        font = default_font()
        w, h = font.measure(text, _HINT_SIZE)
        x = self.abs_x + (self.width  - w) / 2
        y = self.abs_y + (self.height - h) / 2
        font.draw(text, x, y, _HINT_SIZE, _HINT_COLOR)
