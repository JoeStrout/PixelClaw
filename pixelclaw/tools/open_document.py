import queue
import threading
import urllib.request
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from agentcore.tool import Tool
from agentcore.workspace import Workspace

from ..document import ImageDocument

_SUPPORTED = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp"}


class OpenDocumentTool(Tool):
    def __init__(self, dialog_queue: "queue.Queue[tuple]") -> None:
        self._dialog_queue = dialog_queue

    @property
    def name(self) -> str:
        return "open_document"

    @property
    def description(self) -> str:
        return (
            "Open an image as a new document. "
            "Omit `path` entirely to show the system Open file dialog. "
            "Pass an http/https URL to download and open the image. "
            "Pass a file path or bare filename to open from disk — "
            "a bare name is searched next to all currently open documents."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "File path, bare filename, or http/https URL. "
                        "Omit entirely to show the Open file dialog."
                    ),
                },
            },
        }

    def execute(self, workspace: Workspace, *, path: str | None = None) -> str:
        if path is None:
            return self._open_via_dialog(workspace)
        if path.startswith("http://") or path.startswith("https://"):
            return self._open_from_url(workspace, path)
        return self._open_from_path(workspace, path)

    # ------------------------------------------------------------------

    def _open_via_dialog(self, workspace: Workspace) -> str:
        event = threading.Event()
        result_holder: list = []
        self._dialog_queue.put((event, result_holder))
        if not event.wait(timeout=120):
            return "Timed out waiting for file dialog."
        paths: list[Path] = result_holder[0]
        if not paths:
            return "No file selected."
        return self._open_paths(workspace, paths)

    def _open_from_url(self, workspace: Workspace, url: str) -> str:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PixelClaw/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
        except Exception as e:
            return f"Failed to download '{url}': {e}"

        try:
            pil = Image.open(BytesIO(data)).convert("RGBA")
        except Exception as e:
            return f"Could not decode image from '{url}': {e}"

        name = Path(url.split("?")[0]).name or "downloaded.png"
        if not Path(name).suffix:
            name += ".png"

        arr = np.array(pil, dtype=np.uint8)
        doc = ImageDocument()
        doc.path = Path(name)
        doc.push(arr, reason="opened from URL")
        workspace.open(doc)
        workspace.add_history("document_opened", name=doc.name, path=url)
        h, w = arr.shape[:2]
        return f"Opened '{doc.name}' from URL: {w}×{h} px."

    def _open_from_path(self, workspace: Workspace, path_str: str) -> str:
        p = Path(path_str)
        if p.exists():
            resolved = p
        elif p.parent == Path("."):
            # Bare filename — search sibling directories of open documents
            resolved = None
            for doc in workspace.documents:
                if doc.file_path:
                    candidate = doc.file_path.parent / p.name
                    if candidate.exists():
                        resolved = candidate
                        break
            if resolved is None:
                return f"File not found: '{path_str}'."
        else:
            return f"File not found: '{path_str}'."

        if resolved.suffix.lower() not in _SUPPORTED:
            return f"Unsupported format: '{resolved.suffix}'."
        return self._open_paths(workspace, [resolved])

    def _open_paths(self, workspace: Workspace, paths: list[Path]) -> str:
        opened, skipped = [], []
        for p in paths:
            if p.suffix.lower() not in _SUPPORTED:
                skipped.append(p.name)
                continue
            try:
                doc = ImageDocument(p)
            except Exception as e:
                skipped.append(f"{p.name} ({e})")
                continue
            workspace.open(doc)
            workspace.add_history("document_opened", name=doc.name, path=str(p))
            opened.append(p.name)
        parts = []
        if opened:
            parts.append(f"Opened: {', '.join(opened)}.")
        if skipped:
            parts.append(f"Skipped: {', '.join(skipped)}.")
        return " ".join(parts) if parts else "Nothing opened."
