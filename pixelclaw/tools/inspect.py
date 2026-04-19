from collections import Counter

import numpy as np

from agentcore.tool import Tool
from agentcore.workspace import Workspace

_HEX = "0123456789ABCDEF"


class InspectTool(Tool):
    @property
    def name(self) -> str:
        return "inspect"

    @property
    def description(self) -> str:
        return (
            "Inspect pixel statistics for the active image or a rectangular sub-region. "
            "Returns per-channel min/max/mean, transparency breakdown, "
            "the detected background color (transparent or a corner-matched RGB), "
            "the tight bounding box of non-background content, "
            "and an 8×8 hex alpha map (0=transparent, F=opaque) for spatial orientation."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "x":      {"type": "integer", "description": "Left edge of region (default: 0)"},
                "y":      {"type": "integer", "description": "Top edge of region (default: 0)"},
                "width":  {"type": "integer", "description": "Width of region (default: full width)"},
                "height": {"type": "integer", "description": "Height of region (default: full height)"},
            },
        }

    def execute(self, workspace: Workspace, *,
                x: int = 0, y: int = 0,
                width: int | None = None, height: int | None = None) -> str:
        doc = workspace.active_document
        if doc is None or doc.image is None:
            return "Error: no active document."

        img = doc.image
        ih, iw = img.shape[:2]
        if width is None:
            width = iw - x
        if height is None:
            height = ih - y

        if x < 0 or y < 0 or x + width > iw or y + height > ih or width <= 0 or height <= 0:
            return f"Error: region ({x},{y},{width}×{height}) out of bounds for {iw}×{ih} image."

        region = img[y:y + height, x:x + width]  # (H, W, 4) uint8

        # Per-channel stats
        lines = [f"Region: {width}×{height} px at ({x},{y})"]
        lines.append("Channel stats (min / max / mean):")
        for i, name in enumerate("RGBA"):
            ch = region[:, :, i].astype(np.float32)
            lines.append(f"  {name}: {int(ch.min()):3d} / {int(ch.max()):3d} / {ch.mean():.1f}")

        # Transparency breakdown
        alpha = region[:, :, 3]
        total = alpha.size
        n_transparent = int((alpha == 0).sum())
        n_opaque      = int((alpha == 255).sum())
        n_semi        = total - n_transparent - n_opaque
        lines.append(
            f"Alpha: {100*n_transparent/total:.0f}% transparent, "
            f"{100*n_semi/total:.0f}% semi, "
            f"{100*n_opaque/total:.0f}% opaque"
        )

        # Background detection + content bbox
        if n_transparent > 0:
            # Transparency present — background is transparent
            lines.append("Background: transparent")
            rows_m = np.any(alpha > 0, axis=1)
            cols_m = np.any(alpha > 0, axis=0)
            if rows_m.any():
                r0b = int(rows_m.argmax())
                r1b = int(len(rows_m) - rows_m[::-1].argmax() - 1)
                c0b = int(cols_m.argmax())
                c1b = int(len(cols_m) - cols_m[::-1].argmax() - 1)
                lines.append(
                    f"Content bbox: x={x+c0b}–{x+c1b}, y={y+r0b}–{y+r1b} "
                    f"({c1b-c0b+1}×{r1b-r0b+1} px)"
                )
            else:
                lines.append("Content bbox: none (fully transparent)")
        else:
            # No transparency — try corner-based background detection
            h_r, w_r = region.shape[:2]
            corners = [
                tuple(region[0,      0,      :3].tolist()),
                tuple(region[0,      w_r-1,  :3].tolist()),
                tuple(region[h_r-1,  0,      :3].tolist()),
                tuple(region[h_r-1,  w_r-1,  :3].tolist()),
            ]
            (bg_rgb, bg_count) = Counter(corners).most_common(1)[0]
            if bg_count >= 2:
                rc, gc, bc = bg_rgb
                bg_hex = f"#{rc:02X}{gc:02X}{bc:02X}"
                lines.append(f"Background: {bg_hex} ({bg_count}/4 corners match)")
                tol = 15
                mask = ~(
                    (np.abs(region[:, :, 0].astype(np.int16) - rc) <= tol) &
                    (np.abs(region[:, :, 1].astype(np.int16) - gc) <= tol) &
                    (np.abs(region[:, :, 2].astype(np.int16) - bc) <= tol)
                )
                rows_m = np.any(mask, axis=1)
                cols_m = np.any(mask, axis=0)
                if rows_m.any():
                    r0b = int(rows_m.argmax())
                    r1b = int(len(rows_m) - rows_m[::-1].argmax() - 1)
                    c0b = int(cols_m.argmax())
                    c1b = int(len(cols_m) - cols_m[::-1].argmax() - 1)
                    lines.append(
                        f"Content bbox: x={x+c0b}–{x+c1b}, y={y+r0b}–{y+r1b} "
                        f"({c1b-c0b+1}×{r1b-r0b+1} px)"
                    )
                else:
                    lines.append("Content bbox: none (image is entirely background color)")
            else:
                lines.append("Background: none detected (no transparency, corners differ)")
                lines.append("Content bbox: full image (no background detected)")

        # Unique colors (RGB only, ignoring alpha)
        unique_colors = len(np.unique(region[:, :, :3].reshape(-1, 3), axis=0))
        lines.append(f"Unique colors (RGB): {unique_colors:,}")

        # 8×8 hex alpha map + color map
        grid_h, grid_w = 8, 8
        cell_h = height / grid_h
        cell_w = width  / grid_w
        alpha_rows, color_rows = [], []
        for gr in range(grid_h):
            r0c = int(gr * cell_h)
            r1c = max(r0c + 1, int((gr + 1) * cell_h))
            alpha_row, color_row = "", []
            for gc in range(grid_w):
                c0c = int(gc * cell_w)
                c1c = max(c0c + 1, int((gc + 1) * cell_w))
                cell = region[r0c:r1c, c0c:c1c]
                mean_a = cell[:, :, 3].mean()
                alpha_row += _HEX[min(15, int(mean_a / 256 * 16))]
                r = int(cell[:, :, 0].mean())
                g = int(cell[:, :, 1].mean())
                b = int(cell[:, :, 2].mean())
                color_row.append(f"{r:02X}{g:02X}{b:02X}")
            alpha_rows.append(alpha_row)
            color_rows.append(" ".join(color_row))

        lines.append("Alpha map (8×8, 0=transparent F=opaque):")
        for row in alpha_rows:
            lines.append("  " + row)
        lines.append("Color map (8×8, avg RGB per cell as RRGGBB hex):")
        for row in color_rows:
            lines.append("  " + row)

        return "\n".join(lines)
