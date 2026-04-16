"""
Texture cache for PixelClaw.

Converts numpy RGBA arrays to Raylib textures and caches them by document identity.
Two caches are maintained: thumbnails (small, for the Dock) and display textures
(full-size, for the Main panel).

Call unload_all() before CloseWindow().
"""

from __future__ import annotations

from typing import Any

import numpy as np
import raylib as rl
from PIL import Image as PILImage

from .document import ImageDocument

THUMB_MAX = 112   # max dimension for dock thumbnails


def _np_to_pil(arr: np.ndarray) -> PILImage.Image:
    """Convert an RGBA uint8 ndarray (H, W, 4) to a PIL Image."""
    return PILImage.fromarray(arr, "RGBA")


def _pil_to_texture(img: PILImage.Image, filter: int = rl.TEXTURE_FILTER_POINT) -> Any:
    """Upload a PIL RGBA image to the GPU and return a Raylib Texture."""
    rgba = img.convert("RGBA")
    w, h = rgba.size
    raw  = rgba.tobytes()
    buf  = rl.ffi.new("unsigned char[]", raw)   # owned copy — safe after function returns
    rl_img = rl.ffi.new("Image *", {
        "data":    buf,
        "width":   w,
        "height":  h,
        "mipmaps": 1,
        "format":  rl.PIXELFORMAT_UNCOMPRESSED_R8G8B8A8,
    })
    tex = rl.LoadTextureFromImage(rl_img[0])
    rl.SetTextureFilter(tex, filter)
    return tex


# ── thumbnail cache ──────────────────────────────────────────────────────────

_thumb_cache: dict[int, Any] = {}   # id(doc) → Texture


def get_thumbnail(doc: ImageDocument) -> Any | None:
    """Return a cached thumbnail Texture for *doc*, creating it on first call."""
    if doc.image is None:
        return None
    key = id(doc)
    if key not in _thumb_cache:
        thumb = _np_to_pil(doc.image)
        thumb.thumbnail((THUMB_MAX, THUMB_MAX), PILImage.LANCZOS)
        _thumb_cache[key] = _pil_to_texture(thumb, rl.TEXTURE_FILTER_BILINEAR)
    return _thumb_cache[key]


def invalidate_thumbnail(doc: ImageDocument) -> None:
    """Discard the cached thumbnail so it is rebuilt on the next draw."""
    key = id(doc)
    if key in _thumb_cache:
        rl.UnloadTexture(_thumb_cache.pop(key))


# ── display texture cache ─────────────────────────────────────────────────────

_display_cache: dict[int, Any] = {}   # id(doc) → Texture


def get_display_texture(doc: ImageDocument) -> Any | None:
    """Return a cached full-size Texture for *doc*, creating it on first call."""
    if doc.image is None:
        return None
    key = id(doc)
    if key not in _display_cache:
        _display_cache[key] = _pil_to_texture(_np_to_pil(doc.image))
    return _display_cache[key]


def invalidate_display(doc: ImageDocument) -> None:
    """Discard the cached display texture so it is rebuilt on the next draw."""
    key = id(doc)
    if key in _display_cache:
        rl.UnloadTexture(_display_cache.pop(key))


# ── lifecycle ─────────────────────────────────────────────────────────────────

def unload_all() -> None:
    """Unload every cached texture. Call once before CloseWindow()."""
    for tex in list(_thumb_cache.values()):
        rl.UnloadTexture(tex)
    _thumb_cache.clear()
    for tex in list(_display_cache.values()):
        rl.UnloadTexture(tex)
    _display_cache.clear()
