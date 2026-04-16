from agentcore.context import Context

from .document import ImageDocument


class ImageWorkspace(Context[ImageDocument]):
    def __init__(self) -> None:
        super().__init__()
        # Pixel-space selection rectangle (x, y, width, height), or None
        self.selection: tuple[int, int, int, int] | None = None
