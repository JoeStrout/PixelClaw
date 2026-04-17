import numpy as np
from PIL import Image

from agentcore.tool import Tool
from agentcore.workspace import Workspace

_DEFAULT_MODEL = "isnet-general-use"


class RemoveBackgroundTool(Tool):
    @property
    def name(self) -> str:
        return "remove_background"

    @property
    def description(self) -> str:
        return (
            "Remove the background from the active image using a neural network, "
            "making it transparent. Works on photos, cartoons, illustrations, and people. "
            "The model is downloaded on first use (~100–370 MB depending on model).\n\n"
            "Available models:\n"
            "  isnet-general-use  — best all-around default (~180 MB)\n"
            "  isnet-anime        — cartoons, illustrations, anime art (~180 MB)\n"
            "  birefnet-general   — highest quality for photos (~370 MB)\n"
            "  birefnet-general-lite — good quality, smaller download (~100 MB)\n"
            "  u2net_human_seg    — optimized for people and portraits (~170 MB)\n"
            "  bria-rmbg          — excellent quality; non-commercial license (~180 MB)\n"
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "model": {
                    "type": "string",
                    "description": (
                        f"Which model to use. Default: {_DEFAULT_MODEL}. "
                        "Choose isnet-anime for cartoons/illustrations, "
                        "birefnet-general for best photo quality, "
                        "u2net_human_seg for people."
                    ),
                },
            },
        }

    def execute(self, workspace: Workspace, *, model: str = _DEFAULT_MODEL) -> str:
        doc = workspace.active_document
        if doc is None or doc.image is None:
            return "Error: no active document."

        workspace.post_message(f"Removing background with {model}…")

        try:
            from rembg import new_session, remove
        except ImportError:
            return "Error: rembg is not installed."

        session = new_session(model)
        pil_in = Image.fromarray(doc.image, "RGBA")
        pil_out = remove(pil_in, session=session)
        result = np.array(pil_out.convert("RGBA"))

        idx = doc.push(result, f"remove background ({model})")
        h, w = result.shape[:2]
        return f"Background removed from '{doc.name}' ({w}×{h} px) using {model}. Version index: {idx}."
