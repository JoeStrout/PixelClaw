from pathlib import Path

import numpy as np

from agentcore.tool import Tool
from agentcore.workspace import Workspace

from ..document import ImageDocument


class NewImageTool(Tool):
    @property
    def name(self) -> str:
        return "new_image"

    @property
    def description(self) -> str:
        return (
            "Create a new blank image filled with a solid color. "
            "Use this for any 'blank', 'white', 'black', 'transparent', or solid-color canvas — "
            "never use generate_image for solid fills. "
            "Color is RGBA (0–255 each); default is fully transparent [0,0,0,0]."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "width":  {"type": "integer", "description": "Width in pixels"},
                "height": {"type": "integer", "description": "Height in pixels"},
                "color":  {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 3,
                    "maxItems": 4,
                    "description": "Fill color as [R, G, B] or [R, G, B, A] (0–255). Default: [0,0,0,0].",
                },
                "name": {"type": "string", "description": "Document name (optional)"},
            },
            "required": ["width", "height"],
        }

    def execute(self, workspace: Workspace, *, width: int, height: int,
                color: list[int] | None = None, name: str | None = None) -> str:
        if width <= 0 or height <= 0:
            return "Error: width and height must be positive."
        if width > 8192 or height > 8192:
            return "Error: maximum dimension is 8192."

        rgba = list(color) if color else [0, 0, 0, 0]
        if len(rgba) == 3:
            rgba.append(255)

        arr = np.full((height, width, 4), rgba, dtype=np.uint8)

        doc_name = name or f"new_{width}x{height}"
        doc = ImageDocument()
        doc.path = Path(doc_name)
        doc.push(arr, reason=f"new {width}×{height} image")
        workspace.open(doc)
        workspace.add_history("document_opened", name=doc.name)
        return f"Created '{doc.name}': {width}×{height} px, color {rgba}."
