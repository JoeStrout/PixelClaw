from pathlib import Path

from PIL import Image

from agentcore.document import Document


class ImageDocument(Document):
    def __init__(self, path: Path | None = None):
        super().__init__(path)
        self.image: Image.Image | None = None
        if path:
            self.load(path)

    def load(self, path: Path) -> None:
        self.path = path
        self.image = Image.open(path)
        self.dirty = False

    def save(self, path: Path) -> None:
        if self.image is None:
            raise ValueError("No image to save")
        self.image.save(path)
        self.path = path
        self.dirty = False
