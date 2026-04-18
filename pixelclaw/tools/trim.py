from collections import Counter

import numpy as np

from agentcore.tool import Tool
from agentcore.workspace import Workspace


def _parse_color(s: str) -> tuple[int, int, int] | None:
    """Parse '#RRGGBB' or '#RRGGBBAA' → (R, G, B), or return None on failure."""
    s = s.strip().lstrip('#')
    if len(s) in (6, 8):
        try:
            return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
        except ValueError:
            pass
    return None


def _detect_background(image: np.ndarray) -> tuple[int, int, int] | None:
    """Return the background RGB if ≥3 corners agree, else None."""
    h, w = image.shape[:2]
    corners = [
        tuple(image[0,   0,   :3].tolist()),
        tuple(image[0,   w-1, :3].tolist()),
        tuple(image[h-1, 0,   :3].tolist()),
        tuple(image[h-1, w-1, :3].tolist()),
    ]
    (bg, count) = Counter(corners).most_common(1)[0]
    return bg if count >= 3 else None  # type: ignore[return-value]


class TrimTool(Tool):
    @property
    def name(self) -> str:
        return "trim"

    @property
    def description(self) -> str:
        return (
            "Crop the active image to the tight bounding box of non-background pixels. "
            "Background is auto-detected from the image corners (requires ≥3/4 corners to "
            "share the same color), or can be specified explicitly. "
            "An optional tolerance allows near-background pixels to also be treated as background."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "background": {
                    "type": "string",
                    "description": (
                        "Background color as '#RRGGBB' or '#RRGGBBAA', or 'transparent' to trim "
                        "to non-transparent pixels. Omit to auto-detect from image corners."
                    ),
                },
                "tolerance": {
                    "type": "integer",
                    "description": (
                        "Maximum per-channel difference from the background color that is still "
                        "treated as background (0–255, default 0 for exact match)."
                    ),
                },
            },
        }

    def execute(self, workspace: Workspace, *,
                background: str | None = None,
                tolerance: int = 0) -> str:
        doc = workspace.active_document
        if doc is None or doc.image is None:
            return "Error: no active document."

        image = doc.image
        h, w = image.shape[:2]
        tolerance = max(0, min(255, tolerance))

        # Determine background mode
        if background is None or background.strip().lower() == "auto":
            bg_rgb = _detect_background(image)
            if bg_rgb is None:
                return (
                    "Error: could not auto-detect background "
                    "(fewer than 3/4 corners share the same color). "
                    "Specify background='#RRGGBB' explicitly."
                )
            bg_label = f"#{bg_rgb[0]:02X}{bg_rgb[1]:02X}{bg_rgb[2]:02X} (auto-detected)"
        elif background.strip().lower() == "transparent":
            bg_rgb = None
            bg_label = "transparent"
        else:
            bg_rgb = _parse_color(background)
            if bg_rgb is None:
                return f"Error: could not parse background color '{background}'. Use '#RRGGBB'."
            bg_label = f"#{bg_rgb[0]:02X}{bg_rgb[1]:02X}{bg_rgb[2]:02X}"

        # Build mask of non-background pixels
        if bg_rgb is None:
            # Transparent background — content is non-transparent pixels
            mask = image[:, :, 3] > 0
        elif tolerance == 0:
            rc, gc, bc = bg_rgb
            mask = ~(
                (image[:, :, 0] == rc) &
                (image[:, :, 1] == gc) &
                (image[:, :, 2] == bc)
            )
        else:
            bg_arr = np.array(bg_rgb, dtype=np.int32)
            diff = np.abs(image[:, :, :3].astype(np.int32) - bg_arr).max(axis=2)
            mask = diff > tolerance

        rows_m = np.any(mask, axis=1)
        cols_m = np.any(mask, axis=0)

        if not rows_m.any():
            return f"Error: image contains no non-background pixels (background={bg_label})."

        y0 = int(rows_m.argmax())
        y1 = int(len(rows_m) - rows_m[::-1].argmax() - 1)
        x0 = int(cols_m.argmax())
        x1 = int(len(cols_m) - cols_m[::-1].argmax() - 1)

        result = image[y0:y1+1, x0:x1+1].copy()
        crop_w, crop_h = result.shape[1], result.shape[0]
        reason = workspace.agent_reason or f"trim (background={bg_label}, tolerance={tolerance})"
        idx = doc.push(result, reason)
        return (
            f"Trimmed '{doc.name}' from {w}×{h} to {crop_w}×{crop_h} "
            f"(removed {x0}px left, {w-1-x1}px right, {y0}px top, {h-1-y1}px bottom). "
            f"Background: {bg_label}. Version index: {idx}."
        )
