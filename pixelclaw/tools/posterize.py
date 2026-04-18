import numpy as np
from PIL import Image as PILImage, ImageFilter

from agentcore.tool import Tool
from agentcore.workspace import Workspace


def _ensure_black_white(means: np.ndarray, threshold: float = 60.0) -> np.ndarray:
    """Guarantee pure black and white are in the palette.

    For each of black (0,0,0) and white (255,255,255): if the nearest existing
    color is within `threshold` L2 distance, replace it; otherwise append.
    """
    means = means.copy().astype(np.float32)
    for anchor in (np.array([0., 0., 0.]), np.array([255., 255., 255.])):
        dists = np.linalg.norm(means - anchor, axis=1)
        nearest_i = int(np.argmin(dists))
        if dists[nearest_i] <= threshold:
            means[nearest_i] = anchor
        else:
            means = np.vstack([means, anchor])
    return means


def _despeckle(label_map: np.ndarray, n_labels: int) -> np.ndarray:
    """Replace isolated pixels (no neighbor shares the same label) with the modal neighbor label."""
    shifts = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    neighbor_stack = np.stack(
        [np.roll(np.roll(label_map, dr, axis=0), dc, axis=1) for dr, dc in shifts],
        axis=-1,
    )  # (H, W, 8)
    is_isolated = np.all(neighbor_stack != label_map[:, :, np.newaxis], axis=-1)
    if not is_isolated.any():
        return label_map
    vote_counts = np.zeros((*label_map.shape, n_labels), dtype=np.uint8)
    for k in range(n_labels):
        vote_counts[:, :, k] = (neighbor_stack == k).sum(axis=-1)
    mode_neighbors = np.argmax(vote_counts, axis=-1)
    result = label_map.copy()
    result[is_isolated] = mode_neighbors[is_isolated]
    return result


class PosterizeTool(Tool):
    @property
    def name(self) -> str:
        return "posterize"

    @property
    def description(self) -> str:
        return (
            "Posterize the active image by reducing it to a small palette of colors, "
            "removing speckle and texture (common in AI-generated images) while preserving "
            "overall color areas. A blurred copy is used for palette discovery so that "
            "fine texture is ignored; the original pixels are then snapped to the palette."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "palette": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 64,
                    "description": "Maximum number of colors in the output palette. Default: 8.",
                },
                "blend_radius": {
                    "type": "number",
                    "minimum": 0,
                    "description": (
                        "Gaussian blur radius (pixels) applied before palette discovery. "
                        "Higher values ignore finer texture. Default: 4.0."
                    ),
                },
                "despeckle": {
                    "type": "boolean",
                    "description": (
                        "After palette remapping, replace isolated pixels (no neighbor shares "
                        "their color) with the most common neighboring color. Default: true."
                    ),
                },
            },
        }

    def execute(self, workspace: Workspace, *,
                palette: int = 8,
                blend_radius: float = 4.0,
                despeckle: bool = True) -> str:
        from sklearn.mixture import BayesianGaussianMixture

        doc = workspace.active_document
        if doc is None or doc.image is None:
            return "Error: no active image."

        arr = doc.image  # RGBA uint8, shape (H, W, 4)
        h, w = arr.shape[:2]

        has_alpha = arr.shape[2] == 4
        rgb = arr[:, :, :3]
        alpha = arr[:, :, 3] if has_alpha else None

        workspace.post_message(
            f"Posterizing with palette={palette}, blend_radius={blend_radius}…"
        )

        # Blur RGB for palette discovery (ignore speckle/texture).
        pil_rgb = PILImage.fromarray(rgb, "RGB")
        if blend_radius > 0:
            pil_blurred = pil_rgb.filter(ImageFilter.GaussianBlur(radius=blend_radius))
        else:
            pil_blurred = pil_rgb
        blurred = np.asarray(pil_blurred, dtype=np.float32)

        # Fit BGM on blurred pixels (subsample for speed on large images).
        flat_blurred = blurred.reshape(-1, 3)
        n_pixels = flat_blurred.shape[0]
        max_fit_pixels = 50_000
        if n_pixels > max_fit_pixels:
            rng = np.random.default_rng(42)
            idx = rng.choice(n_pixels, max_fit_pixels, replace=False)
            fit_pixels = flat_blurred[idx]
        else:
            fit_pixels = flat_blurred

        bgm = BayesianGaussianMixture(
            n_components=palette,
            covariance_type="full",
            max_iter=200,
            random_state=42,
        )
        bgm.fit(fit_pixels)

        # Extract active palette colors (components with non-negligible weight).
        weights = bgm.weights_
        means = bgm.means_  # shape (palette, 3)
        active = weights > (1.0 / (10 * palette))
        active_means = means[active]
        if len(active_means) == 0:
            active_means = means  # fallback: use all
        active_means = _ensure_black_white(active_means)

        # Snap original pixels to nearest palette color.
        flat_rgb = rgb.reshape(-1, 3).astype(np.float32)
        # Vectorized nearest-neighbor: (N,1,3) - (1,K,3) → distances
        diff = flat_rgb[:, np.newaxis, :] - active_means[np.newaxis, :, :]
        dist2 = (diff ** 2).sum(axis=2)
        nearest = np.argmin(dist2, axis=1).reshape(h, w)
        if despeckle:
            nearest = _despeckle(nearest, len(active_means))
        result_flat = active_means[nearest.reshape(-1)].clip(0, 255).astype(np.uint8)
        result_rgb = result_flat.reshape(h, w, 3)

        if has_alpha:
            result = np.concatenate([result_rgb, alpha[:, :, np.newaxis]], axis=2)
        else:
            result = np.dstack([result_rgb, np.full((h, w), 255, dtype=np.uint8)])

        actual_colors = len(active_means)
        reason = workspace.agent_reason or f"posterize palette={palette} blur={blend_radius}"
        idx = doc.push(result, reason=reason)
        return (
            f"Posterized {w}×{h}: {actual_colors} active colors "
            f"(requested {palette}), blend_radius={blend_radius}. "
            f"Version index: {idx}."
        )


if __name__ == "__main__":
    from pathlib import Path

    def _prompt(msg, default):
        val = input(f"{msg} [{default}]: ").strip()
        return val if val else str(default)

    src = _prompt("Input image path", "input.png")
    palette = int(_prompt("Palette size (colors)", 8))
    blend_radius = float(_prompt("Blur radius (pixels)", 4.0))
    despeckle = _prompt("Despeckle (true/false)", "true").lower() in ("true", "1", "yes")

    from sklearn.mixture import BayesianGaussianMixture

    img = PILImage.open(src).convert("RGBA")
    arr = np.asarray(img)
    h, w = arr.shape[:2]
    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3]

    print(f"Image: {w}×{h}, palette={palette}, blend_radius={blend_radius}")

    pil_rgb = PILImage.fromarray(rgb, "RGB")
    if blend_radius > 0:
        pil_blurred = pil_rgb.filter(ImageFilter.GaussianBlur(radius=blend_radius))
    else:
        pil_blurred = pil_rgb
    blurred = np.asarray(pil_blurred, dtype=np.float32)

    flat_blurred = blurred.reshape(-1, 3)
    n_pixels = flat_blurred.shape[0]
    max_fit_pixels = 50_000
    if n_pixels > max_fit_pixels:
        rng = np.random.default_rng(42)
        idx = rng.choice(n_pixels, max_fit_pixels, replace=False)
        fit_pixels = flat_blurred[idx]
    else:
        fit_pixels = flat_blurred

    print("Fitting BGM…")
    bgm = BayesianGaussianMixture(
        n_components=palette,
        covariance_type="full",
        max_iter=200,
        random_state=42,
    )
    bgm.fit(fit_pixels)

    weights = bgm.weights_
    means = bgm.means_
    active = weights > (1.0 / (10 * palette))
    active_means = means[active]
    if len(active_means) == 0:
        active_means = means
    active_means = _ensure_black_white(active_means)
    print(f"Active palette colors: {len(active_means)} of {palette} (including black & white)")

    print("Remapping pixels…")
    flat_rgb = rgb.reshape(-1, 3).astype(np.float32)
    diff = flat_rgb[:, np.newaxis, :] - active_means[np.newaxis, :, :]
    dist2 = (diff ** 2).sum(axis=2)
    nearest = np.argmin(dist2, axis=1).reshape(h, w)
    if despeckle:
        print("Despckling…")
        nearest = _despeckle(nearest, len(active_means))
    result_flat = active_means[nearest.reshape(-1)].clip(0, 255).astype(np.uint8)
    result_rgb = result_flat.reshape(h, w, 3)

    result = np.concatenate([result_rgb, alpha[:, :, np.newaxis]], axis=2)

    stem = Path(src).stem
    out_path = Path(src).with_name(f"{stem}_posterized.png")
    PILImage.fromarray(result, "RGBA").save(out_path)
    print(f"Saved to {out_path}")
