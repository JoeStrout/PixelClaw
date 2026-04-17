from agentcore.tool import Tool
from agentcore.workspace import Workspace


class CloseDocsTool(Tool):
    @property
    def name(self) -> str:
        return "close_documents"

    @property
    def description(self) -> str:
        return (
            "Close one or more documents by name. "
            "Pass [\"all except active\"] to close every document except the current one."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of document names to close, "
                        "or [\"all except active\"] as a special value."
                    ),
                },
            },
            "required": ["names"],
        }

    def execute(self, workspace: Workspace, *, names: list[str]) -> str:
        if names == ["all except active"]:
            active = workspace.active_document
            to_close = [d.name for d in workspace.documents if d is not active]
        else:
            to_close = names

        closed, missing = [], []
        for name in to_close:
            idx = next((i for i, d in enumerate(workspace.documents) if d.name == name), None)
            if idx is None:
                missing.append(name)
            else:
                workspace.close(idx)
                closed.append(name)

        parts = []
        if closed:
            parts.append(f"Closed: {', '.join(closed)}.")
        if missing:
            parts.append(f"Not found: {', '.join(missing)}.")
        return " ".join(parts) if parts else "Nothing to close."
