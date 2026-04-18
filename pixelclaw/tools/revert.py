from agentcore.tool import Tool
from agentcore.workspace import Workspace


class RevertTool(Tool):
    @property
    def name(self) -> str:
        return "revert"

    @property
    def description(self) -> str:
        return (
            "Revert the active document to a previous version by index. "
            "All versions after the given index are discarded. "
            "Use version_history to find the right index first."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "index": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Version index to revert to (from version_history).",
                },
            },
            "required": ["index"],
        }

    def execute(self, workspace: Workspace, *, index: int) -> str:
        doc = workspace.active_document
        if doc is None:
            return "Error: no active document."
        total = len(doc.version_history())
        if not doc.revert_to(index):
            return f"Error: index {index} out of range (document has {total} versions, 0–{total - 1})."
        _, reason = doc.version_history()[-1]
        h, w = doc.image.shape[:2]
        return (f"Reverted '{doc.name}' to version {index} ({reason or 'no reason recorded'}). "
                f"{total - index - 1} version(s) discarded. Current image: {w}×{h} px.")
