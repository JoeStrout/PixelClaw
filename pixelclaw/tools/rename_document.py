from pathlib import Path

from agentcore.tool import Tool
from agentcore.workspace import Workspace

from ..document import ImageDocument


class RenameDocumentTool(Tool):
    @property
    def name(self) -> str:
        return "rename_document"

    @property
    def description(self) -> str:
        return (
            "Rename a document. Updates the document's display name and, if the document "
            "has a file on disk, renames that file too. "
            "The new name may include an extension; if omitted, the current extension is kept."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "new_name": {
                    "type": "string",
                    "description": (
                        "New filename for the document, e.g. 'lobster2' or 'lobster2.png'. "
                        "Directory path is ignored — only the filename part is used."
                    ),
                },
                "document": {
                    "type": "string",
                    "description": "Name of the document to rename. Defaults to the active document.",
                },
            },
            "required": ["new_name"],
        }

    def execute(self, workspace: Workspace, *,
                new_name: str,
                document: str | None = None) -> str:
        # Resolve document
        if document:
            doc = next((d for d in workspace.documents if d.name == document), None)
            if doc is None:
                return f"Error: no document named '{document}'."
        else:
            doc = workspace.active_document
            if doc is None:
                return "Error: no active document."

        # Build new filename: keep current extension if new_name has none
        new_stem = Path(new_name)
        if new_stem.suffix:
            new_filename = new_stem.name          # e.g. "lobster2.jpg"
        else:
            current_ext = Path(doc.name).suffix or ".png"
            new_filename = new_stem.stem + current_ext   # e.g. "lobster2.png"

        old_name = doc.name

        # Rename file on disk if one exists
        disk_note = ""
        if doc.file_path and doc.file_path.exists():
            new_file_path = doc.file_path.parent / new_filename
            try:
                doc.file_path.rename(new_file_path)
                doc.file_path = new_file_path
                disk_note = f" (file renamed on disk to '{new_file_path}')"
            except Exception as e:
                return f"Error renaming file on disk: {e}"
        elif doc.file_path:
            # file_path set but file doesn't exist — just update the path
            doc.file_path = doc.file_path.parent / new_filename

        doc.path = Path(new_filename)
        return f"Renamed '{old_name}' to '{new_filename}'{disk_note}."
