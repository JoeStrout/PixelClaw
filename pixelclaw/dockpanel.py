from __future__ import annotations

from typing import Any

import raylib as rl

from agentcore.context import Context
from agentcore.panel import Panel
from agentcore.resources import default_font

from .document import ImageDocument
from . import textures

_PAD          = 8     # margin around each item
_NAME_SIZE    = 11.0  # font size for document name
_NAME_GAP     = 4     # gap between thumbnail and name
_ITEM_GAP     = 4     # gap between items
_ACTIVE_TINT  = (255, 255, 255, 255)   # full brightness when active
_INACTIVE_TINT= (140, 140, 140, 255)   # dimmed when not active
_ACTIVE_BORDER= (100, 160, 255, 255)
_BG_ACTIVE    = (55,  55,  80, 255)    # highlight behind active item


class DockPanel(Panel):
    """
    Sidebar panel that shows one thumbnail + name per open document.
    Clicking a thumbnail makes that document active in the context.
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

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _thumb_w(self) -> float:
        return self.width - _PAD * 2

    def _item_height(self, tex: Any | None) -> float:
        """Height of one dock item (thumbnail + name)."""
        font       = default_font()
        _, name_h  = font.measure("Ag", _NAME_SIZE)
        thumb_w    = self._thumb_w()
        if tex is not None:
            aspect    = tex.height / max(tex.width, 1)
            thumb_h   = thumb_w * aspect
        else:
            thumb_h   = thumb_w   # placeholder square
        return thumb_h + _NAME_GAP + name_h + _PAD * 2

    def _item_y(self, index: int) -> float:
        """Top y of item *index* in local coordinates."""
        y = _PAD
        for i, doc in enumerate(self._context.documents):
            if i == index:
                return y
            tex = textures.get_thumbnail(doc) if isinstance(doc, ImageDocument) else None
            y += self._item_height(tex) + _ITEM_GAP
        return y

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self) -> None:
        super().draw()
        ax, ay = self.abs_x, self.abs_y

        rl.BeginScissorMode(int(ax), int(ay), int(self.width), int(self.height))

        y = ay + _PAD
        thumb_w = self._thumb_w()

        for i, doc in enumerate(self._context.documents):
            tex     = textures.get_thumbnail(doc) if isinstance(doc, ImageDocument) else None
            is_active = (i == self._context.active_index)
            item_h  = self._item_height(tex)

            # Active background
            if is_active:
                rl.DrawRectangle(int(ax), int(y), int(self.width), int(item_h), _BG_ACTIVE)

            if tex is not None:
                aspect  = tex.height / max(tex.width, 1)
                thumb_h = thumb_w * aspect
                dest    = rl.ffi.new("Rectangle *", [ax + _PAD, y, thumb_w, thumb_h])
                src     = rl.ffi.new("Rectangle *", [0, 0, float(tex.width), float(tex.height)])
                origin  = rl.ffi.new("Vector2 *", [0.0, 0.0])
                tint    = _ACTIVE_TINT if is_active else _INACTIVE_TINT
                rl.DrawTexturePro(tex, src[0], dest[0], origin[0], 0.0, tint)
                # Border around active thumbnail
                if is_active:
                    rl.DrawRectangleLinesEx(dest[0], 2, _ACTIVE_BORDER)
                name_y = y + thumb_h + _NAME_GAP
            else:
                # Placeholder rectangle when no texture yet
                rl.DrawRectangle(int(ax + _PAD), int(y), int(thumb_w), int(thumb_w),
                                 (80, 80, 80, 255))
                name_y = y + thumb_w + _NAME_GAP

            # Document name, truncated to fit
            font     = default_font()
            name     = doc.name
            max_w    = thumb_w
            while name and font.measure(name, _NAME_SIZE)[0] > max_w:
                name = name[:-1]
            if name != doc.name:
                name = name[:-1] + "…"
            name_color = (220, 220, 220, 255) if is_active else (160, 160, 160, 255)
            font.draw(name, ax + _PAD, name_y, _NAME_SIZE, name_color)

            y += item_h + _ITEM_GAP

        rl.EndScissorMode()

    # ------------------------------------------------------------------
    # Mouse: click to activate
    # ------------------------------------------------------------------

    def on_mouse_press(self, x: float, y: float, button: int) -> bool:
        if button != rl.MOUSE_BUTTON_LEFT:
            return False
        local_y = _PAD
        for i, doc in enumerate(self._context.documents):
            tex    = textures.get_thumbnail(doc) if isinstance(doc, ImageDocument) else None
            item_h = self._item_height(tex)
            if local_y <= y < local_y + item_h:
                self._context.active_index = i
                return True
            local_y += item_h + _ITEM_GAP
        return False
