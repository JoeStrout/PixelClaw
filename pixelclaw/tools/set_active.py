from agentcore.tool import Tool
from agentcore.workspace import Workspace


class SetActiveTool(Tool):
    @property
    def name(self) -> str:
        return "set_active"

    @property
    def description(self) -> str:
        return "Make a named document the active document."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Document name to activate."},
            },
            "required": ["name"],
        }

    def execute(self, workspace: Workspace, *, name: str) -> str:
        for i, doc in enumerate(workspace.documents):
            if doc.name == name:
                workspace.active_index = i
                return f"'{name}' is now the active document."
        names = [d.name for d in workspace.documents]
        return f"Error: no document named '{name}'. Open documents: {names}"
