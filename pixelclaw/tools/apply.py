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


def _run(code: str, ns: dict) -> np.ndarray:
    """Evaluate code as an expression or a multi-line block assigning to `result`."""
    try:
        compile(code, "<string>", "eval")
        return eval(code, ns)  # noqa: S307
    except SyntaxError:
        pass
    exec(code, ns)  # noqa: S102
    result = ns.get("result")
    if result is None:
        raise ValueError("Multi-line code must assign the output array to `result`.")
    return result


class ApplyTool(Tool):
    @property
    def name(self) -> str:
        return "apply"

    @property
    def description(self) -> str:
        return (
            "Apply Python/numpy code to the active image. "
            "`img` is a float32 array of shape (H, W, 4), values 0–255, channels R=0 G=1 B=2 A=3. "
            "Single expression: return value is used. "
            "Multi-line code block: assign the output array to `result`. "
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
                        "A Python expression or multi-line code block that transforms `img` "
                        "(float32 H×W×4, 0–255) into an array of the same shape. "
                        "Single expression: the value is used directly. "
                        "Multi-line: assign output to `result`.\n"
                        "Example (expression): np.clip((img - 128) * 1.5 + 128, 0, 255)\n"
                        "Example (multi-line):\n"
                        "  alpha = img[:,:,3] / 255.0\n"
                        "  glow = ndi.gaussian_filter(alpha, sigma=10) * 255\n"
                        "  result = np.stack([glow, glow, 0*glow, np.clip(img[:,:,3] + glow, 0, 255)], axis=2)"
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

        img = src.astype(np.float32)
        code = textwrap.dedent(expression).strip()
        ns = {**_NAMESPACE, "img": img}

        try:
            result = _run(code, ns)
        except Exception as e:
            return f"Error: {e}"

        if not isinstance(result, np.ndarray):
            return f"Error: code produced {type(result).__name__}, expected ndarray."
        if result.shape != src.shape:
            return f"Error: code produced shape {result.shape}, expected {src.shape}."

        out = np.clip(result, 0, 255).astype(np.uint8)
        reason = workspace.agent_reason or f"apply: {code[:60]}{'…' if len(code) > 60 else ''}"
        idx = doc.push(out, reason)
        h, w = out.shape[:2]
        return f"Applied to '{doc.name}' ({w}×{h}). Version index: {idx}."
