from agentcore.tool import Tool
from agentcore.workspace import Workspace


class UndoTool(Tool):
    @property
    def name(self) -> str:
        return "undo"

    @property
    def description(self) -> str:
        return (
            "Undo the last operation on the active document, reverting to the previous version. "
            "Shortcut for revert(current_version_count - 2). "
            "Use revert with an explicit index to go back further."
        )

    @property
    def input_schema(self) -> dict:
        return {"type": "object", "properties": {}}

    def execute(self, workspace: Workspace) -> str:
        doc = workspace.active_document
        if doc is None:
            return "Error: no active document."
        total = len(doc.version_history())
        if total < 2:
            return "Error: nothing to undo (already at the original version)."
        index = total - 2
        doc.revert_to(index)
        _, reason = doc.version_history()[-1]
        h, w = doc.image.shape[:2]
        return (f"Undid last operation on '{doc.name}'. "
                f"Now at version {index} ({reason or 'no reason recorded'}). "
                f"Current image: {w}×{h} px.")
