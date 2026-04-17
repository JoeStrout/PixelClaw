import base64
import io
from pathlib import Path

import numpy as np
from PIL import Image

from agentcore.tool import Tool
from agentcore.workspace import Workspace
from ..document import ImageDocument


class GenerateImageTool(Tool):
    def __init__(self, openai_api_key: str | None = None) -> None:
        self._api_key = openai_api_key

    @property
    def name(self) -> str:
        return "generate_image"

    @property
    def description(self) -> str:
        return (
            "Generate a brand-new image from a text prompt using gpt-image-1 "
            "and open it as a new document. Use this when the user wants to create "
            "an image from scratch rather than modify an existing one."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed description of the image to generate.",
                },
                "name": {
                    "type": "string",
                    "description": "Filename for the new document (e.g. 'sunset.png'). "
                                   "Defaults to 'generated.png'.",
                },
                "size": {
                    "type": "string",
                    "enum": ["1024x1024", "1536x1024", "1024x1536", "auto"],
                    "description": "Output dimensions. Default: 1024x1024.",
                },
                "quality": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Image quality. Default: medium.",
                },
            },
            "required": ["prompt"],
        }

    def execute(self, workspace: Workspace, *, prompt: str,
                name: str = "generated.png",
                size: str = "1024x1024",
                quality: str = "medium") -> str:
        if not self._api_key:
            return "Error: no API key found (provide openai_key.secret, or api_key.secret if it holds an OpenAI key)."

        workspace.post_message(f'Generating image: "{prompt[:80]}"…')

        import openai
        client = openai.OpenAI(api_key=self._api_key)

        try:
            response = client.images.generate(
                model="gpt-image-1",
                prompt=prompt,
                n=1,
                size=size,
                quality=quality,
            )
        except Exception as e:
            return f"Error from OpenAI: {e}"

        image_data = base64.b64decode(response.data[0].b64_json)
        pil_image = Image.open(io.BytesIO(image_data)).convert("RGBA")
        array = np.array(pil_image)

        doc = ImageDocument()
        doc.path = Path(name)
        doc.push(array, reason=f"generated: {prompt[:80]}")
        workspace.open(doc)

        h, w = array.shape[:2]
        return f"Generated '{name}' ({w}×{h} px) and opened as a new document."
