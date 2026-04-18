from pathlib import Path

import numpy as np
from PIL import Image as PILImage

from agentcore.tool import Tool
from agentcore.workspace import Workspace
from ..document import ImageDocument

# Palette entries with max(R,G,B) below this are treated as black-like
_BLACK_THRESH = 64
# Palette entries with min(R,G,B) above this are treated as white-like
_WHITE_THRESH = 224


def _detect_background(rgb: np.ndarray) -> np.ndarray:
    """Sample border pixels and return the most common color as the background."""
    border = np.concatenate([
        rgb[0, :],          # top row
        rgb[-1, :],         # bottom row
        rgb[1:-1, 0],       # left column (excluding corners)
        rgb[1:-1, -1],      # right column (excluding corners)
    ], axis=0)              # (N, 3)
    # Round to nearest 8 to merge near-identical colors before voting
    quantized = (border.astype(int) // 8 * 8)
    keys, counts = np.unique(quantized.reshape(-1, 3), axis=0, return_counts=True)
    return keys[counts.argmax()].astype(np.uint8)


def _find_fill_palette(rgb: np.ndarray, n_colors: int) -> np.ndarray:
    """Use pyxelate's BGM to find fill colors. Returns (N, 3) uint8.

    Near-black and near-white entries are filtered out; they are handled
    separately as the ink and background layers.
    """
    from pyxelate import Pyx
    pyx = Pyx(palette=n_colors, svd=False)
    pyx.fit(rgb)
    colors = pyx.colors.reshape(-1, 3).astype(np.uint8)
    keep = (colors.max(axis=1) >= _BLACK_THRESH) & (colors.min(axis=1) <= _WHITE_THRESH)
    return colors[keep]


def _two_nearest_mix(pixels: np.ndarray, palette: np.ndarray):
    """For each pixel (N,3) find the two nearest palette entries and the mix weight.

    Returns idx_A (N,), idx_B (N,), alpha (N,) where:
        pixel ≈ alpha * palette[A] + (1-alpha) * palette[B]
    """
    diff = pixels[:, np.newaxis, :].astype(float) - palette[np.newaxis, :, :].astype(float)
    sq = (diff ** 2).sum(axis=2)                   # (N, P)

    idx_A = sq.argmin(axis=1)
    sq2 = sq.copy()
    sq2[np.arange(len(pixels)), idx_A] = np.inf
    idx_B = sq2.argmin(axis=1)

    A = palette[idx_A].astype(float)
    B = palette[idx_B].astype(float)
    P = pixels.astype(float)
    d = A - B
    denom = (d * d).sum(axis=1)
    alpha = np.where(denom > 0, ((P - B) * d).sum(axis=1) / denom, 0.5)
    return idx_A, idx_B, np.clip(alpha, 0, 1)


def separate_layers(
    rgba: np.ndarray,
    n_colors: int = 8,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Split a cartoon RGBA image into ink, color, and background layers.

    Uses pyxelate's Bayesian Gaussian Mixture to find the fill palette, then
    unmixes each pixel as a linear blend of its two nearest palette entries
    (which include synthetic black and white entries for the ink / background).

    Returns four RGBA uint8 arrays:
        ink        — pure black with varying alpha (outlines)
        color      — flat fill colors with varying alpha
        background — pure white with varying alpha
        palette_preview — a 32-px-tall strip showing the discovered fill palette
    """
    h, w = rgba.shape[:2]
    orig_alpha = rgba[:, :, 3].astype(float) / 255.0
    rgb = rgba[:, :, :3]

    # Purify near-black pixels before palette fitting so speckle in dark areas
    # doesn't produce spurious dark fill colors in the BGM.
    rgb_clean = rgb.copy()
    rgb_clean[rgb_clean.max(axis=2) < _BLACK_THRESH] = 0

    bg_color = _detect_background(rgb_clean)               # (3,) uint8

    fill_palette = _find_fill_palette(rgb_clean, n_colors)   # (F, 3)
    # Also remove any palette entry that is very close to the detected background
    if len(fill_palette) > 0:
        bg_dist = np.abs(fill_palette.astype(int) - bg_color.astype(int)).max(axis=1)
        fill_palette = fill_palette[bg_dist > 32]
    if len(fill_palette) == 0:
        fill_palette = np.array([[128, 128, 128]], dtype=np.uint8)

    # Extended palette: 0=black, 1=background, 2..=fill colors
    BLACK_IDX, WHITE_IDX = 0, 1
    palette = np.vstack([
        np.array([[0, 0, 0]]),
        bg_color[np.newaxis],
        fill_palette,
    ]).astype(float)

    pixels = rgb_clean.reshape(-1, 3)
    idx_A, idx_B, alpha = _two_nearest_mix(pixels, palette)

    n = h * w
    ink_w  = np.zeros(n)
    bg_w   = np.zeros(n)
    fill_w = np.zeros(n)
    fill_idx = np.zeros(n, dtype=int)   # index into fill_palette

    Ab = idx_A == BLACK_IDX;  Aw = idx_A == WHITE_IDX;  Af = idx_A >= 2
    Bb = idx_B == BLACK_IDX;  Bw = idx_B == WHITE_IDX;  Bf = idx_B >= 2

    def _set(mask, iw, bw, fw, fi_src):
        ink_w[mask]  = iw(mask)
        bg_w[mask]   = bw(mask)
        fill_w[mask] = fw(mask)
        if fi_src is not None:
            fill_idx[mask] = fi_src(mask) - 2

    z = lambda _: 0.0
    # A=black B=fill
    m = Ab & Bf; _set(m, lambda m: alpha[m],   z, lambda m: 1-alpha[m], lambda m: idx_B[m])
    # A=fill  B=black
    m = Af & Bb; _set(m, lambda m: 1-alpha[m], z, lambda m: alpha[m],   lambda m: idx_A[m])
    # A=white B=fill
    m = Aw & Bf; _set(m, z, lambda m: alpha[m],   lambda m: 1-alpha[m], lambda m: idx_B[m])
    # A=fill  B=white
    m = Af & Bw; _set(m, z, lambda m: 1-alpha[m], lambda m: alpha[m],   lambda m: idx_A[m])
    # A=black B=white
    m = Ab & Bw; _set(m, lambda m: alpha[m],   lambda m: 1-alpha[m], z, None)
    # A=white B=black
    m = Aw & Bb; _set(m, lambda m: 1-alpha[m], lambda m: alpha[m],   z, None)
    # A=fill  B=fill  (solid fill pixel; use nearest)
    m = Af & Bf; _set(m, z, z, lambda _: 1.0, lambda m: idx_A[m])
    # A=black B=black
    m = Ab & Bb; ink_w[m] = 1.0
    # A=white B=white
    m = Aw & Bw; bg_w[m] = 1.0

    oa = orig_alpha.ravel()

    ink = np.zeros((n, 4), dtype=np.uint8)
    ink[:, 3] = np.clip(ink_w * oa * 255, 0, 255).astype(np.uint8)

    color = np.zeros((n, 4), dtype=np.uint8)
    color[:, :3] = fill_palette[fill_idx]
    color[:, 3]  = np.clip(fill_w * oa * 255, 0, 255).astype(np.uint8)

    bg = np.empty((n, 4), dtype=np.uint8)
    bg[:, :3] = bg_color
    bg[:, 3]  = 255  # fully opaque

    # Palette preview strip: each color as a 32×32 swatch
    sw = 32
    strip = np.zeros((sw, sw * len(fill_palette), 4), dtype=np.uint8)
    for i, c in enumerate(fill_palette):
        strip[:, i*sw:(i+1)*sw, :3] = c
        strip[:, i*sw:(i+1)*sw, 3]  = 255

    return (
        ink.reshape(h, w, 4),
        color.reshape(h, w, 4),
        bg.reshape(h, w, 4),
        strip,
    )


class SeparateLayersTool(Tool):
    @property
    def name(self) -> str:
        return "separate_layers"

    @property
    def description(self) -> str:
        return (
            "Split a cartoon/line-art image into layers using palette-based unmixing. "
            "Discovers fill colors via pyxelate's Bayesian Gaussian Mixture, then treats "
            "each pixel as a linear blend of its two nearest palette entries (including "
            "synthetic black and white) to build: "
            "'_ink' (outlines, black with alpha), "
            "'_color' (flat fills, transparent elsewhere), "
            "'_bg' (white background, transparent elsewhere), and "
            "'_palette' (swatch strip of discovered fill colors)."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "n_colors": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 32,
                    "description": "Number of fill colors for pyxelate to find. Default: 8.",
                },
            },
        }

    def execute(self, workspace: Workspace, *, n_colors: int = 8) -> str:
        doc = workspace.active_document
        if doc is None or doc.image is None:
            return "Error: no active image."

        workspace.post_message(
            f"Finding palette ({n_colors} colors) and separating layers… "
            "(this may take a moment)"
        )

        stem = doc.name.rsplit(".", 1)[0] if "." in doc.name else doc.name
        ink_arr, color_arr, bg_arr, palette_arr = separate_layers(doc.image, n_colors)

        n_fill = palette_arr.shape[1] // 32
        for suffix, arr in (
            ("_ink",     ink_arr),
            ("_color",   color_arr),
            ("_bg",      bg_arr),
            ("_palette", palette_arr),
        ):
            name = stem + suffix + ".png"
            new_doc = ImageDocument()
            new_doc.path = Path(name)
            new_doc.push(arr, reason="separate_layers")
            workspace.open(new_doc)

        return (
            f"Created '{stem}_ink', '_color', '_bg', '_palette' from '{doc.name}' "
            f"({doc.image.shape[1]}×{doc.image.shape[0]} px). "
            f"Fill palette has {n_fill} color(s) after filtering black/white."
        )


if __name__ == "__main__":
    src = input("Input image path: ").strip() or "input.png"
    n = input("Number of fill colors [8]: ").strip()
    n_colors = int(n) if n else 8

    img = PILImage.open(src).convert("RGBA")
    rgba = np.asarray(img, dtype=np.uint8)

    print(f"Finding palette ({n_colors} colors) and separating layers…")
    ink, color, bg, palette_strip = separate_layers(rgba, n_colors)

    stem = Path(src).stem
    parent = Path(src).parent
    for suffix, arr in (("_ink", ink), ("_color", color), ("_bg", bg), ("_palette", palette_strip)):
        out = parent / f"{stem}{suffix}.png"
        PILImage.fromarray(arr, "RGBA").save(out)
        print(f"Saved {out}")
