import json
from pathlib import Path
from typing import Any

import raylib as rl


class NinePatch:
    """
    A 9-slice image loaded from a PNG with a companion JSON sidecar defining border widths.

    Sidecar format (same name as PNG, .json extension):
        { "left": 32, "top": 32, "right": 32, "bottom": 32 }

    Usage:
        patch = NinePatch(Path("agentcore/resources/speechBalloonLeft.png"))
        patch.draw(x, y, width, height)
        patch.unload()
    """

    def __init__(self, path: Path) -> None:
        self._texture: Any = rl.LoadTexture(str(path).encode())

        sidecar = path.with_suffix(".json")
        borders = json.loads(sidecar.read_text())
        self._left   = int(borders["left"])
        self._top    = int(borders["top"])
        self._right  = int(borders["right"])
        self._bottom = int(borders["bottom"])

        w = self._texture.width
        h = self._texture.height
        self._info = rl.ffi.new("NPatchInfo *", {
            "source": [0.0, 0.0, float(w), float(h)],
            "left":   self._left,
            "top":    self._top,
            "right":  self._right,
            "bottom": self._bottom,
            "layout": rl.NPATCH_NINE_PATCH,
        })

    def draw(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        tint: Any = None,
    ) -> None:
        """Draw the 9-slice image stretched into the given rectangle."""
        if tint is None:
            tint = rl.WHITE
        dest = rl.ffi.new("Rectangle *", [x, y, width, height])
        origin = rl.ffi.new("Vector2 *", [0.0, 0.0])
        rl.DrawTextureNPatch(self._texture, self._info[0], dest[0], origin[0], 0.0, tint)

    def unload(self) -> None:
        rl.UnloadTexture(self._texture)
