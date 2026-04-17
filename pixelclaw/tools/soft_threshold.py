import numpy as np
from scipy.ndimage import binary_fill_holes, distance_transform_edt

from agentcore.tool import Tool
from agentcore.workspace import Workspace

_CHANNELS = ("luminance", "alpha", "red", "green", "blue")


def _extract_channel(arr: np.ndarray, channel: str) -> np.ndarray:
    if channel == "luminance":
        return (arr[:, :, 0].astype(float) * 0.299 +
                arr[:, :, 1].astype(float) * 0.587 +
                arr[:, :, 2].astype(float) * 0.114)
    idx = {"red": 0, "green": 1, "blue": 2, "alpha": 3}[channel]
    return arr[:, :, idx].astype(float)


def _write_channel(arr: np.ndarray, channel: str, values: np.ndarray) -> np.ndarray:
    out = arr.copy()
    if channel == "luminance":
        v = np.clip(values, 0, 255).astype(np.uint8)
        out[:, :, 0] = v
        out[:, :, 1] = v
        out[:, :, 2] = v
    else:
        idx = {"red": 0, "green": 1, "blue": 2, "alpha": 3}[channel]
        out[:, :, idx] = np.clip(values, 0, 255).astype(np.uint8)
    return out


class SoftThresholdTool(Tool):
    @property
    def name(self) -> str:
        return "soft_threshold"

    @property
    def description(self) -> str:
        return (
            "Clean up a grayscale mask by snapping interior pixels to 0 or 255 while "
            "preserving anti-aliased edges. Works by:\n"
            "1. Thresholding a channel to binary foreground/background.\n"
            "2. Flood-filling enclosed holes in the binary mask.\n"
            "3. Computing each pixel's distance from the nearest binary edge.\n"
            "4. Pixels closer than min_dist keep their original value (anti-aliasing intact).\n"
            "5. Pixels farther than max_dist snap to 255 (foreground) or 0 (background).\n"
            "6. Pixels in between are interpolated.\n"
            "Useful for cleaning up alpha masks with interior noise or small holes."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "enum": list(_CHANNELS),
                    "description": "Which channel to read and write. Default: 'luminance'.",
                },
                "threshold": {
                    "type": "number",
                    "description": "Value (0–255) that separates foreground from background. Default: 128.",
                },
                "min_dist": {
                    "type": "number",
                    "description": "Pixels closer than this to the binary edge keep their original value. Default: 2.",
                },
                "max_dist": {
                    "type": "number",
                    "description": "Pixels farther than this from the binary edge snap to 0 or 255. Default: 7.",
                },
            },
        }

    def execute(self, workspace: Workspace, *,
                channel: str = "luminance",
                threshold: float = 128.0,
                min_dist: float = 2.0,
                max_dist: float = 7.0) -> str:
        doc = workspace.active_document
        if doc is None or doc.image is None:
            return "Error: no active image."
        if channel not in _CHANNELS:
            return f"Error: channel must be one of {_CHANNELS}."
        if min_dist >= max_dist:
            return "Error: min_dist must be less than max_dist."

        arr = doc.image
        gray = _extract_channel(arr, channel)

        # Binary foreground mask, padded by 1 so edge-touching regions are fillable.
        binary = gray > threshold
        h, w = binary.shape
        padded = np.zeros((h + 2, w + 2), dtype=bool)
        padded[1:-1, 1:-1] = binary
        filled_padded = binary_fill_holes(padded)
        filled = filled_padded[1:-1, 1:-1]

        # Distance from the edge of the filled binary mask.
        # Interior pixels of the foreground get positive distances.
        # Interior pixels of the background (holes now filled) also get positive.
        # We want distance from any transition between filled foreground and background.
        dist_fg = distance_transform_edt(filled)    # dist inside foreground
        dist_bg = distance_transform_edt(~filled)   # dist inside background
        dist = np.where(filled, dist_fg, dist_bg)

        # Snap target: filled binary → 255 or 0
        snap = np.where(filled, 255.0, 0.0)

        # Blend factor: 0 at min_dist (keep original), 1 at max_dist (snap)
        blend = np.clip((dist - min_dist) / (max_dist - min_dist), 0.0, 1.0)
        result_channel = gray * (1.0 - blend) + snap * blend

        result = _write_channel(arr, channel, result_channel)
        idx = doc.push(result, reason=workspace.agent_reason or f"soft_threshold {channel} t={threshold} [{min_dist},{max_dist}]")

        changed = int(np.sum(np.abs(result_channel - gray) > 1))
        return (
            f"Applied soft_threshold to '{channel}' channel "
            f"(threshold={threshold}, min_dist={min_dist}, max_dist={max_dist}). "
            f"{changed} pixels modified. Version index: {idx}."
        )
