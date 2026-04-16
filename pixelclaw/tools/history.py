from agentcore.tool import Tool
from agentcore.workspace import Workspace


class VersionHistoryTool(Tool):
    @property
    def name(self) -> str:
        return "version_history"

    @property
    def description(self) -> str:
        return "List all saved versions of the active document, with their index and the reason each was created."

    @property
    def input_schema(self) -> dict:
        return {"type": "object", "properties": {}}

    def execute(self, workspace: Workspace) -> str:
        doc = workspace.active_document
        if doc is None:
            return "Error: no active document."
        history = doc.version_history()
        if not history:
            return "No versions found."
        lines = [f"Version history for '{doc.name}' ({len(history)} versions):"]
        for idx, reason in history:
            marker = " ← current" if idx == len(history) - 1 else ""
            lines.append(f"  [{idx}] {reason or '(no reason)'}{marker}")
        return "\n".join(lines)
