from pathlib import Path

import numpy as np
from PIL import Image

from agentcore.tool import Tool
from agentcore.workspace import Workspace

from ..document import ImageDocument


def _save_with_backup(image: np.ndarray, path: Path) -> None:
    """Write *image* to *path*, backing up the original to <stem>.bak<ext> if needed."""
    if path.exists():
        bak = path.with_name(path.stem + ".bak" + path.suffix)
        if not bak.exists():
            path.rename(bak)

    pil = Image.fromarray(image, "RGBA")
    if path.suffix.lower() in (".jpg", ".jpeg"):
        bg = Image.new("RGB", pil.size, (255, 255, 255))
        bg.paste(pil, mask=pil.split()[3])
        bg.save(path)
    else:
        pil.save(path)


class SaveDocumentTool(Tool):
    @property
    def name(self) -> str:
        return "save_document"

    @property
    def description(self) -> str:
        return (
            "Save a document to disk. "
            "If a file already exists at the destination, the original is first moved to "
            "<stem>.bak<ext> (only if that backup file does not already exist). "
            "Saving as JPEG composites the image onto white before writing. "
            "Never shows a file-picker dialog."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "document": {
                    "type": "string",
                    "description": "Name of the document to save. Defaults to the active document.",
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Destination file path. May be absolute, or just a filename "
                        "(in which case the document's current directory is used). "
                        "If omitted, saves to the document's current file_path. "
                        "A bare name without extension defaults to .png."
                    ),
                },
            },
            "required": [],
        }

    def execute(self, workspace: Workspace, *,
                document: str | None = None,
                path: str | None = None) -> str:
        # Resolve document
        if document:
            doc = next((d for d in workspace.documents if d.name == document), None)
            if doc is None:
                return f"Error: no document named '{document}'."
        else:
            doc = workspace.active_document
            if doc is None:
                return "Error: no active document."

        if not isinstance(doc, ImageDocument) or doc.image is None:
            return f"Error: '{doc.name}' has no image data."

        # Resolve save path
        if path:
            dest = Path(path)
            if not dest.suffix:
                dest = dest.with_suffix(".png")
            if not dest.is_absolute() and doc.file_path:
                dest = doc.file_path.parent / dest
        elif doc.file_path:
            dest = doc.file_path
        else:
            return (
                f"Error: '{doc.name}' has no file path. "
                "Provide a 'path' argument to specify where to save."
            )

        try:
            _save_with_backup(doc.image, dest)
            doc.path = dest
            doc.file_path = dest
            doc.dirty = False
            return f"Saved '{doc.name}' to '{dest}'."
        except Exception as e:
            return f"Error saving '{doc.name}': {e}"


if __name__ == "__main__":
    src = input("Source image: ").strip()
    dest = input("Save to: ").strip()
    img = np.array(Image.open(src).convert("RGBA"))
    _save_with_backup(img, Path(dest))
    print(f"Saved to {dest}")
