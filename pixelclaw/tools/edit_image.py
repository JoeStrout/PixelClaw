import base64
import io

import numpy as np
from PIL import Image

from agentcore.tool import Tool
from agentcore.workspace import Workspace


class EditImageTool(Tool):
    def __init__(self, openai_api_key: str | None = None) -> None:
        self._api_key = openai_api_key

    @property
    def name(self) -> str:
        return "edit_image"

    @property
    def description(self) -> str:
        return (
            "Edit the active image using a natural-language prompt via gpt-image-1. "
            "Examples: 'make this look like a watercolor painting', "
            "'change the lighting to nighttime', 'add snow to the scene'. "
            "If a selection rectangle is set, only that region is replaced; "
            "otherwise the whole image is used as context."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Description of the desired edit or transformation.",
                },
                "quality": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Output quality. Default: medium.",
                },
            },
            "required": ["prompt"],
        }

    def execute(self, workspace: Workspace, *, prompt: str,
                quality: str = "medium") -> str:
        if not self._api_key:
            return "Error: no API key found (provide openai_key.secret, or api_key.secret if it holds an OpenAI key)."

        doc = workspace.active_document
        if doc is None or doc.image is None:
            return "Error: no active document."

        src = doc.image  # uint8 RGBA (H, W, 4)

        # Build mask from selection if present; alpha=0 means "edit here"
        selection = getattr(workspace, "selection", None)
        mask_bytes = None
        if selection:
            x, y, w, h = selection
            ih, iw = src.shape[:2]
            mask = np.full((ih, iw, 4), 255, dtype=np.uint8)
            mask[y:y + h, x:x + w, 3] = 0  # transparent = edit zone
            mask_bytes = _to_png_bytes(mask)

        image_bytes = _to_png_bytes(src)

        workspace.post_message(f'Editing image: "{prompt[:80]}"…')

        import openai
        client = openai.OpenAI(api_key=self._api_key)

        ih, iw = src.shape[:2]
        size = _nearest_size(iw, ih)

        try:
            kwargs: dict = dict(
                model="gpt-image-1",
                prompt=prompt,
                n=1,
                size=size,
                quality=quality,
                image=("image.png", image_bytes, "image/png"),
            )
            if mask_bytes:
                kwargs["mask"] = ("mask.png", mask_bytes, "image/png")
            response = client.images.edit(**kwargs)
        except Exception as e:
            return f"Error from OpenAI: {e}"

        result_data = base64.b64decode(response.data[0].b64_json)
        result_pil = Image.open(io.BytesIO(result_data)).convert("RGBA")
        result_array = np.array(result_pil)

        reason = workspace.agent_reason or f"edit: {prompt[:60]}{'…' if len(prompt) > 60 else ''}"
        idx = doc.push(result_array, reason)
        rh, rw = result_array.shape[:2]
        return f"Edited '{doc.name}' ({rw}×{rh} px). Version index: {idx}."


def _to_png_bytes(array: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(array, "RGBA").save(buf, format="PNG")
    return buf.getvalue()


def _nearest_size(w: int, h: int) -> str:
    """Pick the gpt-image-1 size closest to the source dimensions."""
    options = [(1024, 1024), (1536, 1024), (1024, 1536)]
    best = min(options, key=lambda s: abs(s[0] - w) + abs(s[1] - h))
    return f"{best[0]}x{best[1]}"
