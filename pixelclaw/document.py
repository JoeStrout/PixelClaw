from pathlib import Path

import numpy as np
from PIL import Image

from agentcore.document import Document


class ImageDocument(Document):
    def __init__(self, path: Path | None = None):
        super().__init__(path)
        self._versions: list[tuple[np.ndarray, str]] = []
        if path:
            self.load(path)

    @property
    def image(self) -> np.ndarray | None:
        """Current image as an RGBA uint8 ndarray (H, W, 4), or None."""
        return self._versions[-1][0] if self._versions else None

    def push(self, array: np.ndarray, reason: str = "") -> int:
        """Append a new version, mark dirty, and return the new version index."""
        self._versions.append((array, reason))
        self.dirty = True
        return len(self._versions) - 1

    def revert_to(self, index: int) -> bool:
        """Discard all versions after *index*. Returns True if successful."""
        if 0 <= index < len(self._versions):
            self._versions = self._versions[:index + 1]
            self.dirty = True
            return True
        return False

    def version_history(self) -> list[tuple[int, str]]:
        """Return list of (index, reason) for all versions."""
        return [(i, reason) for i, (_, reason) in enumerate(self._versions)]

    def load(self, path: Path) -> None:
        self.path = path
        self._versions = [(np.array(Image.open(path).convert("RGBA")), "loaded from file")]
        self.dirty = False

    def save(self, path: Path) -> None:
        if self.image is None:
            raise ValueError("No image to save")
        Image.fromarray(self.image, "RGBA").save(path)
        self.path = path
        self.dirty = False
