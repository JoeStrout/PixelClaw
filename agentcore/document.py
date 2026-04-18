from abc import ABC, abstractmethod
from pathlib import Path


class Document(ABC):
    def __init__(self, path: Path | None = None):
        self.path = path
        self.file_path: Path | None = None  # set only when loaded from or saved to disk
        self.dirty = False

    @property
    def name(self) -> str:
        return self.path.name if self.path else "Untitled"

    def thumbnail_b64(self) -> str | None:
        """Return a base64-encoded PNG thumbnail for vision-capable LLMs, or None."""
        return None

    @abstractmethod
    def load(self, path: Path) -> None: ...

    @abstractmethod
    def save(self, path: Path) -> None: ...
