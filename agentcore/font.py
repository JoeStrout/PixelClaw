from pathlib import Path
from typing import Any

import raylib as rl

charset = (
            " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`"
            "abcdefghijklmnopqrstuvwxyz{|}~"
            "“”‘’—–…•×±"
        )
codepoints = None
codepoints_arr = None

class Font:
    """
    Wraps a TrueType font file with a per-pixel-size cache of loaded Raylib fonts.

    Callers work in logical point sizes and logical pixel coordinates throughout.
    Internally, each font is loaded at (point_size × DPI scale) physical pixels so
    that text renders sharply on HiDPI/Retina displays.  Raylib's logical-to-physical
    coordinate mapping means drawing with fontSize=point_size reproduces exactly
    the loaded physical resolution — no blurring, no double-scaling.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        # Maps physical pixel size → loaded Raylib Font struct
        self._cache: dict[int, Any] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _physical_size(self, point_size: float) -> int:
        """Convert a logical point size to the physical pixel size for the current display."""
        scale = rl.GetWindowScaleDPI().x
        return max(1, round(point_size * scale))

    def _get(self, point_size: float) -> tuple[Any, int]:
        """Return (raylib_font, physical_size), loading and caching if necessary."""
        global codepoints, codepoints_arr
        physical = self._physical_size(point_size)
        if physical not in self._cache:
            if codepoints_arr is None:
                codepoints = sorted(set(ord(c) for c in charset))
                codepoints_arr = rl.ffi.new("int[]", codepoints)
            font = rl.LoadFontEx(str(self._path).encode(), physical, codepoints_arr, len(codepoints))
            rl.SetTextureFilter(font.texture, rl.TEXTURE_FILTER_BILINEAR)
            self._cache[physical] = font
        return self._cache[physical], physical

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def draw(
        self,
        text: str,
        x: float,
        y: float,
        point_size: float,
        color: Any,
        spacing: float = 1.0,
    ) -> None:
        """Draw text at (x, y) in logical pixel coordinates."""
        font, _ = self._get(point_size)
        pos = rl.ffi.new("Vector2 *", [x, y])
        rl.DrawTextEx(font, text.encode(), pos[0], float(point_size), spacing, color)

    def measure(self, text: str, point_size: float, spacing: float = 1.0) -> tuple[float, float]:
        """Return (width, height) of text in logical pixels."""
        font, _ = self._get(point_size)
        size = rl.MeasureTextEx(font, text.encode(), float(point_size), spacing)
        return size.x, size.y

    def unload(self) -> None:
        """Unload all cached Raylib fonts.  Call when the window is closing."""
        for font in self._cache.values():
            rl.UnloadFont(font)
        self._cache.clear()
