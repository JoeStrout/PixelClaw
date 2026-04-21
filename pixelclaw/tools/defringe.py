import numpy as np
from scipy.ndimage import distance_transform_edt

from agentcore.tool import Tool
from agentcore.workspace import Workspace


def _defringe(img: np.ndarray, threshold: int, radius: float) -> tuple[np.ndarray, int]:
    """Replace fringe pixel RGB with nearest fully-opaque neighbor color.

    A "fringe" pixel has alpha between 1 and (threshold-1): semi-transparent
    edge pixels that bleed background color.  For each such pixel we find the
    nearest opaque pixel (via distance transform) and copy its RGB, keeping
    the original alpha intact.
    """
    alpha = img[:, :, 3]
    opaque_mask = alpha >= threshold          # pixels we trust for color
    fringe_mask = (alpha > 0) & ~opaque_mask  # pixels we want to fix

    if not fringe_mask.any():
        return img, 0

    # distance_transform_edt returns, for each non-opaque pixel, the distance
    # to the nearest opaque pixel — and optionally the indices of that pixel.
    _, nearest = distance_transform_edt(~opaque_mask, return_indices=True)
    # nearest shape: (2, H, W); nearest[0] = row index, nearest[1] = col index

    # Only fix fringe pixels within `radius` of an opaque pixel
    dist = distance_transform_edt(~opaque_mask)
    to_fix = fringe_mask & (dist <= radius)

    if not to_fix.any():
        return img, 0

    rows, cols = np.where(to_fix)
    src_rows = nearest[0][rows, cols]
    src_cols = nearest[1][rows, cols]

    out = img.copy()
    out[rows, cols, 0] = img[src_rows, src_cols, 0]
    out[rows, cols, 1] = img[src_rows, src_cols, 1]
    out[rows, cols, 2] = img[src_rows, src_cols, 2]
    # alpha is untouched

    return out, int(len(rows))


class DefringeTool(Tool):
    @property
    def name(self) -> str:
        return "defringe"

    @property
    def description(self) -> str:
        return (
            "Remove background-color fringing from semi-transparent edge pixels. "
            "After a background removal, anti-aliased edge pixels often contain the "
            "original background color mixed into their RGB, causing halos on new "
            "backgrounds. This tool replaces each fringe pixel's RGB with the color "
            "of its nearest fully-opaque neighbor, leaving the alpha channel intact."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "threshold": {
                    "type": "integer",
                    "description": (
                        "Alpha value (1–255) at or above which a pixel is considered "
                        "fully opaque and trusted for color. Pixels with alpha below "
                        "this are treated as fringe. Default: 230."
                    ),
                },
                "radius": {
                    "type": "number",
                    "description": (
                        "Maximum distance (pixels) from an opaque pixel for a fringe "
                        "pixel to be fixed. Keeps the operation local to true edges. "
                        "Default: 3.0."
                    ),
                },
            },
        }

    def execute(self, workspace: Workspace, *,
                threshold: int = 230,
                radius: float = 3.0) -> str:
        doc = workspace.active_document
        if doc is None or doc.image is None:
            return "Error: no active image."
        if doc.image.shape[2] < 4:
            return "Error: image has no alpha channel — defringe requires RGBA."
        if not (1 <= threshold <= 255):
            return "Error: threshold must be between 1 and 255."
        if radius <= 0:
            return "Error: radius must be positive."

        result, changed = _defringe(doc.image, threshold, radius)
        if changed == 0:
            return "No fringe pixels found within the given threshold and radius — image unchanged."

        idx = doc.push(result, reason=workspace.agent_reason or f"defringe threshold={threshold} radius={radius}")
        return f"Defringed {changed} edge pixels (threshold={threshold}, radius={radius}). Version index: {idx}."


if __name__ == "__main__":
    from pathlib import Path
    import sys
    from PIL import Image as PILImage
    import numpy as np

    path = input("Input image path: ").strip()
    img = np.array(PILImage.open(path).convert("RGBA"))
    threshold = int(input("Alpha threshold [230]: ").strip() or 230)
    radius = float(input("Radius [3.0]: ").strip() or 3.0)
    result, changed = _defringe(img, threshold, radius)
    out_path = Path(path).stem + "_defringed.png"
    PILImage.fromarray(result).save(out_path)
    print(f"Fixed {changed} pixels → {out_path}")
