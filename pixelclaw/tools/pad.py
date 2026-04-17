import numpy as np

from agentcore.tool import Tool
from agentcore.workspace import Workspace


def _sample_fill_color(src: np.ndarray) -> list[int]:
    """Return a fill color by sampling all four corners.

    Uses the most common corner color if any two agree; otherwise averages all four.
    """
    h, w = src.shape[:2]
    corners = [
        src[0,   0  ].tolist(),
        src[0,   w-1].tolist(),
        src[h-1, 0  ].tolist(),
        src[h-1, w-1].tolist(),
    ]
    counts: dict[tuple, int] = {}
    for c in corners:
        key = tuple(c)
        counts[key] = counts.get(key, 0) + 1
    best = max(counts, key=lambda k: counts[k])
    if counts[best] >= 2:
        return list(best)
    return [round(sum(c[i] for c in corners) / 4) for i in range(4)]


class PadTool(Tool):
    @property
    def name(self) -> str:
        return "pad"

    @property
    def description(self) -> str:
        return (
            "Add blank border padding around the active image. "
            "Each side is specified independently in pixels."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "top":    {"type": "integer", "minimum": 0, "description": "Pixels to add on top"},
                "bottom": {"type": "integer", "minimum": 0, "description": "Pixels to add on bottom"},
                "left":   {"type": "integer", "minimum": 0, "description": "Pixels to add on left"},
                "right":  {"type": "integer", "minimum": 0, "description": "Pixels to add on right"},
                "color": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0, "maximum": 255},
                    "minItems": 4, "maxItems": 4,
                    "description": "Fill color as [R, G, B, A]. Defaults to the most common corner color of the source image.",
                },
            },
            "required": ["top", "bottom", "left", "right"],
        }

    def execute(self, workspace: Workspace, *, top: int, bottom: int,
                left: int, right: int, color: list[int] | None = None) -> str:
        doc = workspace.active_document
        if doc is None or doc.image is None:
            return "Error: no active image."
        if any(v < 0 for v in (top, bottom, left, right)):
            return "Error: padding values must be non-negative."

        src = doc.image
        rgba = list(color) if color else _sample_fill_color(src)
        oh, ow = src.shape[:2]
        nh, nw = oh + top + bottom, ow + left + right

        result = np.empty((nh, nw, 4), dtype=np.uint8)
        result[:] = rgba
        result[top:top + oh, left:left + ow] = src

        # Alpha-bleed: if the border is transparent, fill its RGB with the nearest
        # edge pixel's RGB so that operations like glow work correctly.
        if rgba[3] == 0:
            if top > 0:
                result[:top, left:left + ow, :3] = src[0:1, :, :3]
            if bottom > 0:
                result[top + oh:, left:left + ow, :3] = src[-1:, :, :3]
            if left > 0:
                result[:, :left, :3] = result[:, left:left + 1, :3]
            if right > 0:
                result[:, left + ow:, :3] = result[:, left + ow - 1:left + ow, :3]

        idx = doc.push(result, reason=workspace.agent_reason or f"pad t{top} b{bottom} l{left} r{right}")
        return f"Padded to {nw}×{nh} px (was {ow}×{oh}). Added {top}px top, {bottom}px bottom, {left}px left, {right}px right. Version index: {idx}."
