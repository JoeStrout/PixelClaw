import base64
import io

import numpy as np
import requests
from PIL import Image

from agentcore.tool import Tool
from agentcore.workspace import Workspace
from ..document import ImageDocument


class PixelateTool(Tool):
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "pixelate"

    @property
    def description(self) -> str:
        return (
            "Convert the active image into low-res pixel art using the Retro Diffusion API. "
            "Opens the result as a new document."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Description of the desired pixel-art style/content. Default: 'pixel art'.",
                },
                "width": {
                    "type": "integer",
                    "description": "Target pixel-art width in pixels. Default: 64.",
                },
                "height": {
                    "type": "integer",
                    "description": "Target pixel-art height in pixels. Default: 64.",
                },
                "prompt_style": {
                    "type": "string",
                    "description": "Retro Diffusion style slug, e.g. 'rd_fast__default', 'rd_fast__rpg_item_pixel_art'. Default: rd_fast__default.",
                },
                "tile": {
                    "type": "boolean",
                    "description": "If true, generate a seamlessly tiling image. Default: false.",
                },
            },
        }

    def execute(self, workspace: Workspace, *,
                prompt: str = "pixel art",
                width: int = 64, height: int = 64,
                prompt_style: str = "rd_fast__default",
                tile: bool = False) -> str:
        if not self._api_key:
            return "Error: no Retro Diffusion API key (provide retro_diffusion_key.secret)."

        doc = workspace.active_document
        if doc is None or doc.image is None:
            return "Error: no active document."

        workspace.post_message(f"Pixelating '{doc.name}' to {width}×{height} with {prompt_style}…")

        pil_img = Image.fromarray(doc.image, "RGBA")
        has_alpha = bool(np.any(doc.image[:, :, 3] < 255))

        # Retro Diffusion rejects large payloads; cap the upload at 512px on the long edge.
        _MAX_UPLOAD = 512
        src_w, src_h = pil_img.size
        if max(src_w, src_h) > _MAX_UPLOAD:
            scale = _MAX_UPLOAD / max(src_w, src_h)
            pil_img = pil_img.resize(
                (max(1, int(src_w * scale)), max(1, int(src_h * scale))),
                Image.LANCZOS,
            )

        buf = io.BytesIO()
        pil_img.convert("RGB").save(buf, format="PNG")
        b64_image = base64.b64encode(buf.getvalue()).decode()

        payload: dict = {
            "prompt_style": prompt_style,
            "prompt": prompt,
            "input_image": b64_image,
            "width": width,
            "height": height,
            "num_images": 1,
        }
        if has_alpha:
            payload["remove_bg"] = True
        if tile:
            payload["tile_x"] = True
            payload["tile_y"] = True

        try:
            resp = requests.post(
                "https://api.retrodiffusion.ai/v1/inferences",
                headers={
                    "X-RD-Token": self._api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.HTTPError as e:
            return f"Error from Retro Diffusion API ({resp.status_code}): {resp.text}"
        except Exception as e:
            return f"Error calling Retro Diffusion API: {e}"

        images = data.get("base64_images") or []
        if not images:
            return f"Error: no images in API response. Response: {data}"

        result_bytes = base64.b64decode(images[0])
        result_pil = Image.open(io.BytesIO(result_bytes)).convert("RGBA")
        result_array = np.array(result_pil)

        stem = doc.path.stem if doc.path else "image"
        new_name = f"{stem}_pixel_{width}x{height}.png"

        new_doc = ImageDocument()
        from pathlib import Path
        new_doc.path = Path(new_name)
        new_doc.push(result_array, reason=f"pixelate {width}×{height} ({model})")
        workspace.open(new_doc)

        cost = data.get("balance_cost", "unknown")
        remaining = data.get("remaining_balance", "unknown")
        h, w = result_array.shape[:2]
        return (
            f"Pixelated '{doc.name}' → '{new_name}' ({w}×{h} px) using {prompt_style}. "
            f"Cost: ${cost}. Remaining balance: ${remaining}."
        )
