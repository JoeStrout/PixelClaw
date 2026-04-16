import numpy as np
from PIL import Image as PILImage

from agentcore.tool import Tool
from agentcore.workspace import Workspace

_RESAMPLE_METHODS = {
    "nearest":  PILImage.NEAREST,
    "bilinear": PILImage.BILINEAR,
    "lanczos":  PILImage.LANCZOS,
}


class ScaleTool(Tool):
    @property
    def name(self) -> str:
        return "scale"

    @property
    def description(self) -> str:
        return (
            "Resize the active image. Provide width, height, or both. "
            "If only one dimension is given, the other is computed to preserve the aspect ratio."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "width": {
                    "type": "integer", "minimum": 1,
                    "description": "Target width in pixels. Omit to derive from height.",
                },
                "height": {
                    "type": "integer", "minimum": 1,
                    "description": "Target height in pixels. Omit to derive from width.",
                },
                "resample": {
                    "type": "string",
                    "enum": ["nearest", "bilinear", "lanczos"],
                    "description": "Resampling filter. Default: 'lanczos' (best quality). Use 'nearest' to preserve hard pixel edges.",
                },
            },
        }

    def execute(self, workspace: Workspace, *,
                width: int | None = None, height: int | None = None,
                resample: str = "lanczos") -> str:
        doc = workspace.active_document
        if doc is None or doc.image is None:
            return "Error: no active image."
        if width is None and height is None:
            return "Error: at least one of 'width' or 'height' must be specified."

        filter_ = _RESAMPLE_METHODS.get(resample, PILImage.LANCZOS)
        oh, ow = doc.image.shape[:2]

        if width is None:
            width = max(1, round(ow * height / oh))
        elif height is None:
            height = max(1, round(oh * width / ow))

        pil = PILImage.fromarray(doc.image, "RGBA")
        result = np.asarray(pil.resize((width, height), resample=filter_))

        idx = doc.push(result, reason=workspace.agent_reason or f"scale to {width}×{height}")
        return f"Scaled from {ow}×{oh} to {width}×{height} px using {resample}. Version index: {idx}."
