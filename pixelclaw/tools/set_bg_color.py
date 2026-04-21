from PIL.ImageColor import getrgb

from agentcore.tool import Tool
from agentcore.workspace import Workspace


class SetBgColorTool(Tool):
    @property
    def name(self) -> str:
        return "set_background"

    @property
    def description(self) -> str:
        return (
            "Set the display background behind the image. "
            "Pass 'checkerboard' for the default transparency pattern, "
            "or any HTML color string (e.g. 'red', '#FF0000', 'rgb(0,128,255)')."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "background": {
                    "type": "string",
                    "description": "'checkerboard' or an HTML color string.",
                },
            },
            "required": ["background"],
        }

    def execute(self, workspace: Workspace, *, background: str) -> str:
        value = background.strip()
        if value.lower() != "checkerboard":
            try:
                getrgb(value)
            except (ValueError, KeyError):
                return f"Error: '{value}' is not a recognized color. Use an HTML color name, hex code, or 'checkerboard'."
        workspace.display_bg = value
        return f"Display background set to '{value}'."
