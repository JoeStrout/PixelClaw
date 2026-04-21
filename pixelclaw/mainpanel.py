from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

import raylib as rl

from agentcore.context import Context
from agentcore.panel import Panel
from agentcore.resources import default_font

from .document import ImageDocument
from . import textures

if TYPE_CHECKING:
    from agentcore.inputfield import InputField

_HINT_COLOR  = (100, 100, 100, 255)
_HINT_SIZE   = 16.0
_MARGIN      = 16.0
_DIM_SIZE    = 12.0
_DIM_COLOR   = (120, 120, 120, 255)
_PIXEL_SIZE  = 12.0
_HASH_COLOR  = (180, 180, 180, 255)
_RED_COLOR   = (255,  60,  60, 255)
_GREEN_COLOR = ( 60, 255,  60, 255)
_BLUE_COLOR  = ( 80, 140, 255, 255)
_ALPHA_COLOR = (160, 160, 160, 255)
_BG_PATTERN  = Path(__file__).parent / "resources" / "backgroundPattern.png"

_COLOR_KW = {"color", "colour"}
_POS_KW   = {"pos", "position", "here"}


def _pick_insertion(field: "InputField", px: int, py: int, color_html: str) -> str:
    text_before = field.text[:field.cursor_pos]
    recent = set(text_before.lower().split()[-2:])
    if recent & _COLOR_KW:
        return color_html
    if recent & _POS_KW:
        return f"(X:{px}, Y:{py})"
    return f"(X:{px}, Y:{py}, {color_html})"


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
        self._input_field: InputField | None = None
        self._focus_input_fn: Callable[[], None] | None = None
        self._window_was_focused: bool = True

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

        # Scale to fit within the margined area while preserving aspect ratio
        avail_w = self.width
        avail_h = self.height - 2 * _MARGIN
        scale  = min(avail_w / tex.width, avail_h / tex.height)
        draw_w = tex.width  * scale
        draw_h = tex.height * scale
        draw_x = self.abs_x + (self.width  - draw_w) / 2
        draw_y = self.abs_y + _MARGIN + (avail_h - draw_h) / 2

        # Background behind the image: checkerboard or solid color
        bg = getattr(self._context, "display_bg", "checkerboard")
        if bg == "checkerboard":
            self._ensure_bg()
            if self._bg_tex.id != 0:
                bg_src  = rl.ffi.new("Rectangle *", [0.0, 0.0, draw_w, draw_h])
                bg_dest = rl.ffi.new("Rectangle *", [draw_x, draw_y, draw_w, draw_h])
                origin  = rl.ffi.new("Vector2 *",   [0.0, 0.0])
                rl.DrawTexturePro(self._bg_tex, bg_src[0], bg_dest[0], origin[0], 0.0, rl.WHITE)
        else:
            from PIL.ImageColor import getrgb as _getrgb
            try:
                rgb = _getrgb(bg)
                color = (rgb[0], rgb[1], rgb[2], rgb[3] if len(rgb) > 3 else 255)
            except (ValueError, KeyError):
                color = (0, 0, 0, 255)
            rl.DrawRectangle(int(draw_x), int(draw_y), int(draw_w), int(draw_h), color)

        src  = rl.ffi.new("Rectangle *", [0.0, 0.0, float(tex.width), float(tex.height)])
        dest = rl.ffi.new("Rectangle *", [draw_x, draw_y, draw_w, draw_h])
        origin = rl.ffi.new("Vector2 *", [0.0, 0.0])
        rl.DrawTexturePro(tex, src[0], dest[0], origin[0], 0.0, rl.WHITE)

        # Dimensions label — right-aligned in the top margin
        font = default_font()
        dim_text = f"{doc.image.shape[1]}×{doc.image.shape[0]}"
        tw, _ = font.measure(dim_text, _DIM_SIZE)
        font.draw(dim_text,
                  self.abs_x + self.width - tw - 4,
                  self.abs_y + (_MARGIN - _DIM_SIZE) / 2,
                  _DIM_SIZE, _DIM_COLOR)

        # Pixel info — bottom gutter, left-aligned, when mouse is over image
        mp = rl.GetMousePosition()
        mx, my = mp.x, mp.y
        if (draw_x <= mx < draw_x + draw_w) and (draw_y <= my < draw_y + draw_h):
            px = int((mx - draw_x) / scale)
            py = int((my - draw_y) / scale)
            img = doc.image
            h_img, w_img = img.shape[:2]
            px = max(0, min(px, w_img - 1))
            py = max(0, min(py, h_img - 1))
            self._context.mouse_image_pos = (px, py)
            pixel = img[py, px]
            r = int(pixel[0]) if len(pixel) > 0 else 0
            g = int(pixel[1]) if len(pixel) > 1 else 0
            b = int(pixel[2]) if len(pixel) > 2 else 0
            a = int(pixel[3]) if len(pixel) > 3 else 255
            coord_text = f"({px}, {py})  "
            hash_text  = "#"
            rr_text    = f"{r:02X}"
            gg_text    = f"{g:02X}"
            bb_text    = f"{b:02X}"
            aa_text    = f"{a:02X}"
            gutter_y = self.abs_y + self.height - (_MARGIN + _PIXEL_SIZE) / 2
            cx = self.abs_x + 8
            cw, _ = font.measure(coord_text, _PIXEL_SIZE)
            font.draw(coord_text, cx, gutter_y, _PIXEL_SIZE, _DIM_COLOR)
            cx += cw
            hw, _ = font.measure(hash_text, _PIXEL_SIZE)
            font.draw(hash_text, cx, gutter_y, _PIXEL_SIZE, _HASH_COLOR)
            cx += hw
            for seg, color in ((rr_text, _RED_COLOR), (gg_text, _GREEN_COLOR),
                               (bb_text, _BLUE_COLOR), (aa_text, _ALPHA_COLOR)):
                sw, _ = font.measure(seg, _PIXEL_SIZE)
                font.draw(seg, cx, gutter_y, _PIXEL_SIZE, color)
                cx += sw
        else:
            self._context.mouse_image_pos = None

    # ------------------------------------------------------------------
    # Mouse input — click on image inserts pixel info into the input field
    # ------------------------------------------------------------------

    def on_mouse_press(self, x: float, y: float, button: int) -> bool:
        if button != rl.MOUSE_BUTTON_LEFT or self._input_field is None:
            return False
        if not self._window_was_focused:
            return False
        doc = self._context.active_document
        if not isinstance(doc, ImageDocument) or doc.image is None:
            return False
        tex = textures.get_display_texture(doc)
        if tex is None:
            return False
        avail_w = self.width
        avail_h = self.height - 2 * _MARGIN
        scale  = min(avail_w / tex.width, avail_h / tex.height)
        draw_w = tex.width  * scale
        draw_h = tex.height * scale
        draw_x = (self.width  - draw_w) / 2      # local coords
        draw_y = _MARGIN + (avail_h - draw_h) / 2
        if not (draw_x <= x < draw_x + draw_w and draw_y <= y < draw_y + draw_h):
            return False
        px = max(0, min(int((x - draw_x) / scale), doc.image.shape[1] - 1))
        py = max(0, min(int((y - draw_y) / scale), doc.image.shape[0] - 1))
        pixel = doc.image[py, px]
        r = int(pixel[0]) if len(pixel) > 0 else 0
        g = int(pixel[1]) if len(pixel) > 1 else 0
        b = int(pixel[2]) if len(pixel) > 2 else 0
        a = int(pixel[3]) if len(pixel) > 3 else 255
        color_html = f"#{r:02X}{g:02X}{b:02X}{a:02X}"
        self._input_field.insert_text(_pick_insertion(self._input_field, px, py, color_html))
        if self._focus_input_fn:
            self._focus_input_fn()
        return True

    def _draw_hint(self, text: str) -> None:
        font = default_font()
        w, h = font.measure(text, _HINT_SIZE)
        x = self.abs_x + (self.width  - w) / 2
        y = self.abs_y + (self.height - h) / 2
        font.draw(text, x, y, _HINT_SIZE, _HINT_COLOR)
