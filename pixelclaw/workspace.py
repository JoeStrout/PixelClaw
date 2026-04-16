from agentcore.context import Context

from .document import ImageDocument


class ImageWorkspace(Context[ImageDocument]):
    def __init__(self) -> None:
        super().__init__()
        # Pixel-space selection rectangle (x, y, width, height), or None
        self.selection: tuple[int, int, int, int] | None = None

    def render_context(self) -> str:
        lines = ["## Current Context\n"]

        if self.current_task:
            lines.append(f"**Current task:** {self.current_task}\n")

        if not self.documents:
            lines.append("**Open documents:** none\n")
        else:
            lines.append("**Open documents:**\n")
            for i, doc in enumerate(self.documents):
                marker = " *(active)*" if i == self.active_index else ""
                lines.append(f"\n### {doc.name}{marker}")
                lines.append(f"- **Path:** {doc.path or 'unsaved'}")
                if doc.image is not None:
                    h, w, c = doc.image.shape
                    depth = doc.image.dtype
                    channel_label = {1: "grayscale", 2: "grayscale+alpha",
                                     3: "RGB", 4: "RGBA"}.get(c, f"{c}-channel")
                    lines.append(f"- **Size:** {w} × {h} px")
                    lines.append(f"- **Channels:** {channel_label} ({c}ch, {depth})")
                    lines.append(f"- **Versions (undo depth):** {len(doc.version_history())}")
                else:
                    lines.append("- *(no image data)*")

        if self.selection:
            x, y, w, h = self.selection
            lines.append(f"\n**Selection:** x={x}, y={y}, w={w}, h={h}")
        else:
            lines.append("\n**Selection:** none")

        return "\n".join(lines)
