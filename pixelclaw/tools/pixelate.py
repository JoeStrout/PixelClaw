import numpy as np
from PIL import Image as PILImage

from agentcore.tool import Tool
from agentcore.workspace import Workspace

_DITHER_METHODS = ["none", "naive", "bayer", "floyd", "atkinson"]


def _resolve_factor(w: int, h: int,
                    factor: int | None,
                    target_w: int | None,
                    target_h: int | None) -> tuple[int, str] | tuple[None, str]:
    """Return (factor, error_string). error_string is empty on success."""

    if target_w is None and target_h is None:
        # Factor-only path (original behaviour).
        return (factor or 8), ""

    # Derive factor from whichever target dimension was given.
    if target_w is not None and target_h is not None:
        f_from_w = max(1, round(w / target_w))
        f_from_h = max(1, round(h / target_h))
        if f_from_w != f_from_h:
            return None, (
                f"target_width={target_w} implies factor {f_from_w} "
                f"but target_height={target_h} implies factor {f_from_h}. "
                "Provide only one target dimension, or make them consistent."
            )
        implied = f_from_w
    elif target_w is not None:
        implied = max(1, round(w / target_w))
    else:
        implied = max(1, round(h / target_h))

    if factor is not None and factor != implied:
        return None, (
            f"factor={factor} conflicts with target size "
            f"(which implies factor={implied}). "
            "Omit one or make them consistent."
        )

    return implied, ""


def _pre_scale(arr: np.ndarray, factor: int,
               target_w: int | None, target_h: int | None) -> np.ndarray:
    """Scale arr so its dimensions are exact multiples of factor."""
    h, w = arr.shape[:2]
    tw = (target_w or round(w / factor)) * factor
    th = (target_h or round(h / factor)) * factor
    if tw == w and th == h:
        return arr
    pil = PILImage.fromarray(arr)
    return np.asarray(pil.resize((tw, th), PILImage.LANCZOS))


class PixelateTool(Tool):
    @property
    def name(self) -> str:
        return "pixelate"

    @property
    def description(self) -> str:
        return (
            "Convert the active image to pixel art using the pyxelate library. "
            "Specify either a downsampling factor or a target output size (width/height or both). "
            "When a target size is given the image is pre-scaled to the nearest exact multiple "
            "before pixelation, so the output matches the requested size precisely. "
            "Providing both factor and target size is allowed only if they are consistent."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "factor": {
                    "type": "integer",
                    "minimum": 2,
                    "description": (
                        "Downsampling factor; output is 1/factor the (pre-scaled) size. "
                        "Omit when specifying target_width/target_height."
                    ),
                },
                "target_width": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Desired output width in pixels. The tool picks the nearest factor.",
                },
                "target_height": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Desired output height in pixels. The tool picks the nearest factor.",
                },
                "palette": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 32,
                    "description": "Number of colors in the output palette. Default: 8.",
                },
                "dither": {
                    "type": "string",
                    "enum": _DITHER_METHODS,
                    "description": "Dithering method. Default: 'none'.",
                },
                "upscale": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Factor to upscale the pixelated result (nearest-neighbor). Default: 1.",
                },
                "svd": {
                    "type": "boolean",
                    "description": "Apply SVD noise reduction before pixelation. Default: false.",
                },
            },
        }

    def execute(self, workspace: Workspace, *,
                factor: int | None = None,
                target_width: int | None = None,
                target_height: int | None = None,
                palette: int = 8,
                dither: str = "none",
                upscale: int = 1,
                svd: bool = False) -> str:
        doc = workspace.active_document
        if doc is None or doc.image is None:
            return "Error: no active image."

        arr = doc.image  # RGBA uint8
        h, w = arr.shape[:2]

        resolved_factor, err = _resolve_factor(w, h, factor, target_width, target_height)
        if err:
            return f"Error: {err}"

        # Pre-scale to an exact multiple of the factor if a target size was requested.
        working = arr
        if target_width is not None or target_height is not None:
            working = _pre_scale(arr, resolved_factor, target_width, target_height)
            pw, ph = working.shape[1], working.shape[0]
        else:
            pw, ph = w, h

        out_w = pw // resolved_factor
        out_h = ph // resolved_factor
        workspace.post_message(
            f"Pixelating {w}×{h} → {out_w}×{out_h} px "
            f"(factor={resolved_factor}, palette={palette})… (this may take a moment)"
        )

        has_alpha = working.shape[2] == 4
        if has_alpha:
            alpha = working[:, :, 3]
            rgb = working[:, :, :3]
        else:
            rgb = working

        try:
            from pyxelate import Pyx
            pyx = Pyx(factor=resolved_factor, palette=palette,
                      dither=dither, upscale=upscale, svd=svd)
            pyx.fit(rgb)
            result_rgb = pyx.transform(rgb)
        except Exception as e:
            return f"Error during pixelation: {e}"

        if has_alpha:
            new_h, new_w = result_rgb.shape[:2]
            pil_alpha = PILImage.fromarray(alpha, "L").resize((new_w, new_h), PILImage.NEAREST)
            new_alpha = np.asarray(pil_alpha)[:, :, np.newaxis]
            result = np.concatenate([result_rgb, new_alpha], axis=2).astype(np.uint8)
        else:
            result = result_rgb.astype(np.uint8)
            result = np.dstack([result, np.full(result.shape[:2], 255, dtype=np.uint8)])

        new_h, new_w = result.shape[:2]
        reason = workspace.agent_reason or f"pixelate factor={resolved_factor} palette={palette} dither={dither}"
        idx = doc.push(result, reason=reason)
        return (
            f"Pixelated {w}×{h} → {new_w}×{new_h} px, "
            f"factor={resolved_factor}, palette={palette}, dither={dither}. "
            f"Version index: {idx}."
        )


if __name__ == "__main__":
    from pathlib import Path
    from pyxelate import Pyx

    def _prompt(msg, default):
        val = input(f"{msg} [{default}]: ").strip()
        return val if val else str(default)

    src = _prompt("Input image path", "input.png")
    raw_factor = input("Downscale factor (leave blank to use target size): ").strip()
    raw_tw     = input("Target width in pixels (leave blank to use factor): ").strip()
    raw_th     = input("Target height in pixels (leave blank to use factor): ").strip()
    palette = int(_prompt("Palette size (colors)", 8))
    dither  = _prompt(f"Dither ({'/'.join(_DITHER_METHODS)})", "none")
    upscale = int(_prompt("Upscale factor", 1))
    svd     = _prompt("SVD noise reduction (true/false)", "false").lower() in ("true", "1", "yes")

    in_factor  = int(raw_factor) if raw_factor else None
    in_tw      = int(raw_tw)     if raw_tw     else None
    in_th      = int(raw_th)     if raw_th     else None

    img = PILImage.open(src).convert("RGBA")
    arr = np.asarray(img)
    h, w = arr.shape[:2]

    resolved_factor, err = _resolve_factor(w, h, in_factor, in_tw, in_th)
    if err:
        raise SystemExit(f"Error: {err}")

    working = arr
    if in_tw is not None or in_th is not None:
        working = _pre_scale(arr, resolved_factor, in_tw, in_th)
        print(f"Pre-scaled to {working.shape[1]}×{working.shape[0]} px (factor={resolved_factor})")

    alpha  = working[:, :, 3]
    rgb    = working[:, :, :3]

    pyx = Pyx(factor=resolved_factor, palette=palette, dither=dither, upscale=upscale, svd=svd)
    pyx.fit(rgb)
    result_rgb = pyx.transform(rgb)

    new_h, new_w = result_rgb.shape[:2]
    pil_alpha = PILImage.fromarray(alpha, "L").resize((new_w, new_h), PILImage.NEAREST)
    new_alpha = np.asarray(pil_alpha)[:, :, np.newaxis]
    result = np.concatenate([result_rgb, new_alpha], axis=2).astype(np.uint8)

    stem = Path(src).stem
    out_path = Path(src).with_name(f"{stem}_pixelated.png")
    PILImage.fromarray(result, "RGBA").save(out_path)
    print(f"Saved {w}×{h} → {new_w}×{new_h} px to {out_path}")
