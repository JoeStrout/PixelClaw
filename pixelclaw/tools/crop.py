from agentcore.tool import Tool
from agentcore.workspace import Workspace


class CropTool(Tool):
    @property
    def name(self) -> str:
        return "crop"

    @property
    def description(self) -> str:
        return "Crop the active image to a rectangular region."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "x":      {"type": "integer", "description": "Left edge of crop region (pixels)"},
                "y":      {"type": "integer", "description": "Top edge of crop region (pixels)"},
                "width":  {"type": "integer", "description": "Width of crop region (pixels)"},
                "height": {"type": "integer", "description": "Height of crop region (pixels)"},
            },
            "required": ["x", "y", "width", "height"],
        }

    def execute(self, workspace: Workspace, *, x: int, y: int, width: int, height: int) -> str:
        doc = workspace.active_document
        if doc is None or doc.image is None:
            return "Error: no active image."
        h, w = doc.image.shape[:2]
        x2, y2 = x + width, y + height
        if x < 0 or y < 0 or x2 > w or y2 > h or width <= 0 or height <= 0:
            return f"Error: crop region ({x},{y},{width}×{height}) out of bounds for {w}×{h} image."
        result = doc.image[y:y2, x:x2].copy()
        idx = doc.push(result, reason=workspace.agent_reason or f"crop {x},{y} {width}×{height}")
        return f"Cropped to {width}×{height} px (from {w}×{h}). Version index: {idx}."
