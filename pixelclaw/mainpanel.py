from __future__ import annotations

import raylib as rl

from agentcore.context import Context
from agentcore.panel import Panel
from agentcore.resources import default_font

from .document import ImageDocument
from . import textures

_HINT_COLOR = (100, 100, 100, 255)
_HINT_SIZE  = 16.0


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
        scale   = min(self.width / tex.width, self.height / tex.height)
        draw_w  = tex.width  * scale
        draw_h  = tex.height * scale
        draw_x  = self.abs_x + (self.width  - draw_w) / 2
        draw_y  = self.abs_y + (self.height - draw_h) / 2

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
