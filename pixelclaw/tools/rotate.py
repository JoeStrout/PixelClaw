import math

import numpy as np
from PIL import Image as PILImage

from agentcore.tool import Tool
from agentcore.workspace import Workspace


def _active_bounds(arr: np.ndarray) -> tuple[int, int, int, int]:
    """Return (x, y, w, h) bounding box of non-transparent pixels, or full image."""
    alpha = arr[:, :, 3]
    rows = np.any(alpha > 0, axis=1)
    cols = np.any(alpha > 0, axis=0)
    if not rows.any():
        h, w = arr.shape[:2]
        return 0, 0, w, h
    y0, y1 = int(np.argmax(rows)), int(len(rows) - 1 - np.argmax(rows[::-1]))
    x0, x1 = int(np.argmax(cols)), int(len(cols) - 1 - np.argmax(cols[::-1]))
    return x0, y0, x1 - x0 + 1, y1 - y0 + 1


def _rotate_point(px: float, py: float, cx: float, cy: float, rad: float) -> tuple[float, float]:
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    dx, dy = px - cx, py - cy
    return cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a


class RotateTool(Tool):
    @property
    def name(self) -> str:
        return "rotate"

    @property
    def description(self) -> str:
        return (
            "Rotate the active image by a given number of degrees (counter-clockwise positive). "
            "The canvas grows automatically so no content is lost. "
            "Pivot defaults to the center of the image; you may specify a custom pivot in pixels."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "degrees": {
                    "type": "number",
                    "description": "Rotation angle in degrees. Positive = counter-clockwise.",
                },
                "pivot_x": {
                    "type": "number",
                    "description": "X coordinate of rotation pivot (pixels). Default: image center.",
                },
                "pivot_y": {
                    "type": "number",
                    "description": "Y coordinate of rotation pivot (pixels). Default: image center.",
                },
                "resample": {
                    "type": "string",
                    "enum": ["nearest", "bilinear", "bicubic", "lanczos"],
                    "description": "Resampling filter. Default: 'bicubic' (good quality). Use 'nearest' for pixel art.",
                },
            },
            "required": ["degrees"],
        }

    def execute(self, workspace: Workspace, *, degrees: float,
                pivot_x: float | None = None, pivot_y: float | None = None,
                resample: str = "bicubic") -> str:
        doc = workspace.active_document
        if doc is None or doc.image is None:
            return "Error: no active image."

        arr = doc.image
        oh, ow = arr.shape[:2]

        cx = pivot_x if pivot_x is not None else ow / 2.0
        cy = pivot_y if pivot_y is not None else oh / 2.0

        # Find the bounding box of active (non-transparent) content.
        bx, by, bw, bh = _active_bounds(arr)

        # Rotate all four corners of the content bounds to find new extents.
        rad = math.radians(degrees)
        corners = [
            (bx,      by),
            (bx + bw, by),
            (bx,      by + bh),
            (bx + bw, by + bh),
        ]
        rotated = [_rotate_point(px, py, cx, cy, rad) for px, py in corners]
        min_x = min(p[0] for p in rotated)
        max_x = max(p[0] for p in rotated)
        min_y = min(p[1] for p in rotated)
        max_y = max(p[1] for p in rotated)

        # New canvas must contain both the original image and the rotated content.
        new_x0 = min(0.0, min_x)
        new_y0 = min(0.0, min_y)
        new_x1 = max(float(ow), max_x)
        new_y1 = max(float(oh), max_y)
        new_w = math.ceil(new_x1 - new_x0)
        new_h = math.ceil(new_y1 - new_y0)

        # Offset: how much the original image origin shifts in the new canvas.
        off_x = int(round(-new_x0))
        off_y = int(round(-new_y0))

        # Paste original onto expanded transparent canvas, then rotate.
        canvas = PILImage.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
        src = PILImage.fromarray(arr, "RGBA")
        canvas.paste(src, (off_x, off_y))

        resample_map = {
            "nearest":  PILImage.NEAREST,
            "bilinear": PILImage.BILINEAR,
            "bicubic":  PILImage.BICUBIC,
            "lanczos":  PILImage.LANCZOS,
        }
        filter_ = resample_map.get(resample, PILImage.BICUBIC)

        # PIL rotate: positive = counter-clockwise, pivot relative to canvas.
        new_cx = cx + off_x
        new_cy = cy + off_y
        rotated_img = canvas.rotate(
            degrees,
            resample=filter_,
            center=(new_cx, new_cy),
            expand=False,
        )

        result = np.asarray(rotated_img)
        reason = workspace.agent_reason or f"rotate {degrees}°"
        idx = doc.push(result, reason=reason)
        return (
            f"Rotated {degrees}° (CCW). "
            f"Original size: {ow}×{oh} px. "
            f"New size: {new_w}×{new_h} px. "
            f"Version index: {idx}."
        )
