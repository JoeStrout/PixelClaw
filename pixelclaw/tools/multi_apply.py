import textwrap
from pathlib import Path

import numpy as np

from agentcore.tool import Tool
from agentcore.workspace import Workspace
from ..document import ImageDocument
from .apply import _NAMESPACE, _run


class MultiApplyTool(Tool):
    @property
    def name(self) -> str:
        return "multi_apply"

    @property
    def description(self) -> str:
        return (
            "Apply Python/numpy code that can read from multiple named documents. "
            "Each entry in `images` maps a variable name to a document name; "
            "those variables are available in the expression as float32 H×W×4 arrays (values 0–255). "
            "The result is written to `result_name`: if that document already exists a new version "
            "is pushed; otherwise a new document is created. "
            "Assign the output array to `result` (multi-line) or return it (single expression). "
            "Available names: np, ndi (scipy.ndimage), skimage."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "images": {
                    "type": "object",
                    "description": (
                        "Mapping of variable_name → document_name. "
                        "E.g. {\"base\": \"park.jpg\", \"overlay\": \"lemming.png\"}. "
                        "Use \"active\" as the document name to refer to the active document. "
                        "Those variables are then usable in `expression`."
                    ),
                    "additionalProperties": {"type": "string"},
                },
                "expression": {
                    "type": "string",
                    "description": (
                        "Python expression or multi-line code block. "
                        "Use the variable names from `images` to access each image. "
                        "Single expression: value is used as result. "
                        "Multi-line: assign output array to `result`.\n"
                        "Example (alpha-composite overlay onto base):\n"
                        "  a = overlay[:,:,3:4] / 255.0\n"
                        "  result = np.clip(overlay * a + base * (1 - a), 0, 255)"
                    ),
                },
                "result_name": {
                    "type": "string",
                    "description": (
                        "Name of the document to write the result to. "
                        "Use \"active\" to write to the active document. "
                        "If the name matches an existing document, a new version is pushed. "
                        "If it is a new name, a new document is created and opened."
                    ),
                },
            },
            "required": ["images", "expression", "result_name"],
        }

    def execute(self, workspace: Workspace, *,
                images: dict[str, str], expression: str, result_name: str) -> str:
        def _resolve(name: str):
            if name == "active":
                return workspace.active_document
            return next((d for d in workspace.documents if d.name == name), None)

        # Resolve variable names → float32 arrays
        ns = dict(_NAMESPACE)
        for var_name, doc_name in images.items():
            doc = _resolve(doc_name)
            if doc is None:
                available = ["active"] + [d.name for d in workspace.documents]
                return f"Error: no document named '{doc_name}'. Available: {available}"
            if doc.image is None:
                return f"Error: document '{doc_name}' has no image data."
            ns[var_name] = doc.image.astype(np.float32)

        code = textwrap.dedent(expression).strip()
        try:
            result = _run(code, ns)
        except Exception as e:
            return f"Error: {e}"

        if not isinstance(result, np.ndarray):
            return f"Error: expression produced {type(result).__name__}, expected ndarray."
        if result.ndim != 3 or result.shape[2] != 4:
            return f"Error: result must be shape (H, W, 4), got {result.shape}."

        out = np.clip(result, 0, 255).astype(np.uint8)
        h, w = out.shape[:2]

        # Resolve result_name: "active" → push to active doc
        target = _resolve(result_name)
        display_name = workspace.active_document.name if result_name == "active" and target else result_name
        reason = workspace.agent_reason or f"multi_apply → {display_name}"

        if target is not None:
            idx = target.push(out, reason)
            return f"Updated '{display_name}' ({w}×{h} px). Version index: {idx}."
        else:
            doc = ImageDocument()
            doc.path = Path(result_name)
            doc.push(out, reason)
            workspace.open(doc)
            return f"Created '{result_name}' ({w}×{h} px)."
