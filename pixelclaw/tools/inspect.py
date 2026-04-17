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
            "the bounding box of non-transparent content, "
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

        # Bounding box of non-transparent pixels
        rows = np.any(alpha > 0, axis=1)
        cols = np.any(alpha > 0, axis=0)
        if rows.any():
            r0, r1 = int(rows.argmax()), int(len(rows) - rows[::-1].argmax() - 1)
            c0, c1 = int(cols.argmax()), int(len(cols) - cols[::-1].argmax() - 1)
            lines.append(
                f"Content bbox: x={x+c0}–{x+c1}, y={y+r0}–{y+r1} "
                f"({c1-c0+1}×{r1-r0+1} px)"
            )
        else:
            lines.append("Content bbox: none (fully transparent)")

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
