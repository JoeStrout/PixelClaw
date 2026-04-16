from abc import ABC, abstractmethod
from pathlib import Path


class Document(ABC):
    def __init__(self, path: Path | None = None):
        self.path = path
        self.dirty = False

    @property
    def name(self) -> str:
        return self.path.name if self.path else "Untitled"

    @abstractmethod
    def load(self, path: Path) -> None: ...

    @abstractmethod
    def save(self, path: Path) -> None: ...
