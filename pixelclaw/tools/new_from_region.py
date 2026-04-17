from pathlib import Path

import numpy as np

from agentcore.tool import Tool
from agentcore.workspace import Workspace
from ..document import ImageDocument


class NewFromRegionTool(Tool):
    @property
    def name(self) -> str:
        return "new_from_region"

    @property
    def description(self) -> str:
        return (
            "Create a new document from a rectangular region of the active image "
            "without modifying the original. Omit x/y/width/height to duplicate the whole image."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name":   {"type": "string",  "description": "Name for the new document (e.g. 'left_third.png')."},
                "x":      {"type": "integer", "description": "Left edge of region (default 0)."},
                "y":      {"type": "integer", "description": "Top edge of region (default 0)."},
                "width":  {"type": "integer", "description": "Width of region (default: full width)."},
                "height": {"type": "integer", "description": "Height of region (default: full height)."},
            },
            "required": ["name"],
        }

    def execute(self, workspace: Workspace, *, name: str,
                x: int = 0, y: int = 0,
                width: int | None = None, height: int | None = None) -> str:
        src_doc = workspace.active_document
        if src_doc is None or src_doc.image is None:
            return "Error: no active document."

        src = src_doc.image
        ih, iw = src.shape[:2]
        if width is None:
            width = iw - x
        if height is None:
            height = ih - y

        if x < 0 or y < 0 or x + width > iw or y + height > ih or width <= 0 or height <= 0:
            return f"Error: region ({x},{y},{width}×{height}) out of bounds for {iw}×{ih} image."

        region = src[y:y + height, x:x + width].copy()

        doc = ImageDocument()
        doc.path = Path(name)
        doc.push(region, reason=f"new from region of '{src_doc.name}'")
        workspace.open(doc)

        return f"Created '{name}' ({width}×{height} px) from '{src_doc.name}' at ({x},{y})."
