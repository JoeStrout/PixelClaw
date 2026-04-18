import json
import textwrap

import numpy as np

from agentcore.tool import Tool
from agentcore.workspace import Workspace


_NAMESPACE = {"np": np}

try:
    import scipy.ndimage as _ndi
    _NAMESPACE["ndi"] = _ndi
except ImportError:
    pass

try:
    import skimage
    _NAMESPACE["skimage"] = skimage
except ImportError:
    pass


def _run(code: str, ns: dict) -> object:
    """Evaluate code as an expression or a block assigning to `result`."""
    try:
        compile(code, "<string>", "eval")
        return eval(code, ns)  # noqa: S307
    except SyntaxError:
        pass
    exec(code, ns)  # noqa: S102
    result = ns.get("result")
    if result is None:
        raise ValueError("Multi-line code must assign the output to `result`.")
    return result


def _format(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(f"{k}: {v}" for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return "\n".join(str(v) for v in value)
    if isinstance(value, np.ndarray):
        return f"Error: code returned an ndarray — use the `apply` tool to transform images."
    return str(value)


class QueryTool(Tool):
    @property
    def name(self) -> str:
        return "query"

    @property
    def description(self) -> str:
        return (
            "Run Python/numpy code on the active image and return a string or dict of results. "
            "Use this to compute bounding boxes, statistics, color values, or any other "
            "information you need before deciding on further actions. "
            "Does NOT modify the image. "
            "`img` is a float32 array of shape (H, W, 4), values 0–255, channels R=0 G=1 B=2 A=3. "
            "`image` is the same data as uint8. "
            "Single expression: return value is used. "
            "Multi-line code block: assign the output to `result`. "
            "Available names: np, ndi (scipy.ndimage), skimage."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": (
                        "A Python expression or multi-line code block that reads `img` "
                        "(float32 H×W×4, 0–255) and produces a string, dict, number, or list. "
                        "Single expression: the value is returned directly. "
                        "Multi-line: assign output to `result`.\n"
                        "Example — find bbox of non-white pixels:\n"
                        "  mask = ~((image[:,:,0]==255) & (image[:,:,1]==255) & (image[:,:,2]==255))\n"
                        "  rows = np.where(np.any(mask, axis=1))[0]\n"
                        "  cols = np.where(np.any(mask, axis=0))[0]\n"
                        "  result = {'x': int(cols[0]), 'y': int(rows[0]), "
                        "'width': int(cols[-1]-cols[0]+1), 'height': int(rows[-1]-rows[0]+1)}"
                    ),
                },
            },
            "required": ["expression"],
        }

    def execute(self, workspace: Workspace, *, expression: str) -> str:
        doc = workspace.active_document
        if doc is None:
            return "Error: no active document."
        src = doc.image
        if src is None:
            return "Error: active document has no image data."

        img   = src.astype(np.float32)
        image = src
        code  = textwrap.dedent(expression).strip()
        ns    = {**_NAMESPACE, "img": img, "image": image}

        try:
            result = _run(code, ns)
        except Exception as e:
            return f"Error: {e}"

        return _format(result)
