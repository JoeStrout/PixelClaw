import cv2
import numpy as np
from PIL import Image as PILImage
from pathlib import Path
from scipy import ndimage

from agentcore.tool import Tool
from agentcore.workspace import Workspace

_BLACK_THRESH   = 64
_DEFAULT_TOL    = 128   # default L∞ tolerance; keeps fill within the seed's color family


# ── mask computation ──────────────────────────────────────────────────────────

def _ink_mask(img: np.ndarray, black_thresh: int = _BLACK_THRESH) -> np.ndarray:
    """(H, W) bool — True where pixel is a fill barrier (dark AND opaque).

    Transparent pixels are never barriers: after remove_background they have
    RGB=(0,0,0) which would otherwise look like ink.
    """
    return (img[:, :, :3].max(axis=2) < black_thresh) & (img[:, :, 3] > 127)



def _fill_mask(img: np.ndarray, seed_x: int, seed_y: int,
               black_thresh: int = _BLACK_THRESH,
               tolerance: int | None = None) -> tuple[np.ndarray, bool, int | None]:
    """(H, W) bool mask of the connected region containing the seed, a dark
    flag indicating which blend formulas to use, and the tolerance actually
    applied (explicit or auto-detected; None if pure ink-bounded fill).

    Light seed — fill the connected non-ink region (ink pixels are barriers).
    Dark seed  — fill the connected dark region (light pixels are barriers).
                 Uses 3× black_thresh to capture anti-aliased edge pixels.

    When tolerance is given, only pixels whose color is within that L∞
    distance of the seed color are candidates — useful for separating
    adjacent flat-colored regions that share no ink boundary.
    """
    seed_max = int(img[seed_y, seed_x, :3].max())
    is_opaque = img[seed_y, seed_x, 3] >= 128
    dark = (seed_max < black_thresh) and is_opaque

    if tolerance is not None:
        seed_color = img[seed_y, seed_x, :3].astype(np.float32)
        diff = np.abs(img[:, :, :3].astype(np.float32) - seed_color).max(axis=2)
        candidates = (diff <= tolerance) & (img[:, :, 3] > 127)
        if not dark:
            candidates &= ~_ink_mask(img, black_thresh)
        labeled, _ = ndimage.label(candidates)
        comp = int(labeled[seed_y, seed_x])
        if comp == 0:
            return np.zeros((img.shape[0], img.shape[1]), dtype=bool), dark, tolerance
        return (labeled == comp), dark, tolerance

    if dark:
        dark_thresh = black_thresh * 3
        fillable = (img[:, :, :3].max(axis=2) < dark_thresh) & (img[:, :, 3] > 127)
        labeled, _ = ndimage.label(fillable)
        comp = int(labeled[seed_y, seed_x])
        if comp == 0:
            return np.zeros((img.shape[0], img.shape[1]), dtype=bool), True, None
        return (labeled == comp), True, None
    else:
        barriers = _ink_mask(img, black_thresh)
        if barriers[seed_y, seed_x]:
            return np.zeros((img.shape[0], img.shape[1]), dtype=bool), False, None

        # Ink-bounded fill — baseline for the tolerance check.
        labeled_notol, _ = ndimage.label(~barriers)
        mask_notol = (labeled_notol == int(labeled_notol[seed_y, seed_x]))

        # Apply default tolerance to stay within the seed's color family.
        # If ink barriers already confine the region (count_tol ≈ count_notol),
        # skip tolerance and use the ink-bounded fill directly.
        seed_color = img[seed_y, seed_x, :3].astype(np.float32)
        diff       = np.abs(img[:, :, :3].astype(np.float32) - seed_color).max(axis=2)
        candidates = (diff <= _DEFAULT_TOL) & (img[:, :, 3] > 127) & ~barriers
        labeled_tol, _ = ndimage.label(candidates)
        comp_tol = int(labeled_tol[seed_y, seed_x])
        if comp_tol > 0:
            mask_tol    = (labeled_tol == comp_tol)
            count_notol = int(mask_notol.sum())
            count_tol   = int(mask_tol.sum())
            if count_tol < count_notol * 0.9:
                return mask_tol, False, _DEFAULT_TOL

        return mask_notol, False, None


# ── applicators ───────────────────────────────────────────────────────────────

def _apply_hsl_blend(img: np.ndarray, mask: np.ndarray,
                     fill_rgb: tuple[int, int, int],
                     dark: bool = False) -> np.ndarray:
    """Recolor masked pixels via HSL blend, using fill color's H and S.

    Light seed (dark=False) — multiply:  result_L = orig_L × fill_L
      White → exact fill color; darker pixels proportionally darker.
    Dark seed  (dark=True)  — screen:    result_L = 1 − (1−orig_L)(1−fill_L)
      Black → exact fill color; lighter pixels proportionally lighter.

    RGB only — caller handles alpha.
    """
    out = img.copy()
    rows, cols = np.where(mask)
    if len(rows) == 0:
        return out

    rgb_f = img[:, :, :3].astype(np.float32) / 255.0
    hls = cv2.cvtColor(rgb_f[:, :, ::-1], cv2.COLOR_BGR2HLS)

    fr, fg, fb = fill_rgb
    fill_bgr = np.array([[[fb / 255.0, fg / 255.0, fr / 255.0]]], dtype=np.float32)
    fill_hls = cv2.cvtColor(fill_bgr, cv2.COLOR_BGR2HLS)
    f_h = float(fill_hls[0, 0, 0])
    f_l = float(fill_hls[0, 0, 1])
    f_s = float(fill_hls[0, 0, 2])

    orig_l = hls[rows, cols, 1]

    if dark:
        result_l = 1.0 - (1.0 - f_l) * (1.0 - orig_l)
    else:
        # Transparent pixels have no meaningful color — treat as white canvas.
        effective_l = orig_l.copy()
        effective_l[img[rows, cols, 3] < 128] = 1.0
        result_l = effective_l * f_l

    result_hls = hls.copy()
    result_hls[rows, cols, 0] = f_h
    result_hls[rows, cols, 1] = result_l
    result_hls[rows, cols, 2] = f_s

    result_bgr = cv2.cvtColor(result_hls, cv2.COLOR_HLS2BGR)
    result_rgb = (result_bgr[:, :, ::-1] * 255.0).clip(0, 255).astype(np.uint8)

    out[rows, cols, 0] = result_rgb[rows, cols, 0]
    out[rows, cols, 1] = result_rgb[rows, cols, 1]
    out[rows, cols, 2] = result_rgb[rows, cols, 2]
    return out


def _apply_alpha_blend(img: np.ndarray, mask: np.ndarray,
                       target_alpha: int,
                       dark: bool = False) -> np.ndarray:
    """Adjust alpha within the fill mask using lightness-based blending.

    Light seed (dark=False): new_α = 255 − (255−target) × L
      White (fill area) → target_alpha; black (ink) → stays 255.
    Dark seed  (dark=True):  new_α = target + (255−target) × L
      Black (ink area) → target_alpha; white (background) → stays 255.

    RGB channels are left unchanged.
    """
    out = img.copy()
    rows, cols = np.where(mask)
    if len(rows) == 0:
        return out
    L = img[rows, cols, :3].astype(np.float32).max(axis=1) / 255.0
    if dark:
        new_alpha = target_alpha + (255.0 - target_alpha) * L
    else:
        new_alpha = 255.0 - (255.0 - target_alpha) * L
    out[rows, cols, 3] = np.clip(new_alpha, 0, 255).astype(np.uint8)
    return out


# ── public entry point ────────────────────────────────────────────────────────

def _flood_fill(img: np.ndarray, seed_x: int, seed_y: int,
                fill_color: tuple[int, int, int, int] = (0, 0, 255, 255),
                mode: str = "color",
                black_thresh: int = _BLACK_THRESH,
                tolerance: int | None = None) -> tuple[np.ndarray, int, int | None]:
    """Flood-fill a region bounded by ink lines.

    Automatically detects whether the seed is on a light or dark pixel and
    selects the matching blend formula (multiply vs screen for color mode,
    or the dual alpha formulas).

    mode="color" — recolor via HSL blend; alpha set to 255.
    mode="alpha" — adjust alpha channel only (0=erase, 255=unerase).

    Returns (result_image, pixel_count, used_tolerance).
    """
    mask, dark, used_tol = _fill_mask(img, seed_x, seed_y, black_thresh, tolerance)
    count = int(mask.sum())
    if mode == "color":
        out = _apply_hsl_blend(img, mask, fill_color[:3], dark=dark)
        out[mask, 3] = 255
        return out, count, used_tol
    if mode == "alpha":
        return _apply_alpha_blend(img, mask, fill_color[3], dark=dark), count, used_tol
    raise ValueError(f"Unknown fill mode: {mode!r}")


# ── tool ──────────────────────────────────────────────────────────────────────

class FillTool(Tool):
    @property
    def name(self) -> str:
        return "fill"

    @property
    def description(self) -> str:
        return (
            "Flood-fill a region bounded by ink/outline pixels.\n"
            "Automatically handles light and dark seeds:\n"
            "  Light seed — fills the non-ink area (e.g. white background, colored body).\n"
            "  Dark seed  — fills the ink area itself (e.g. black outlines, dark eyes).\n"
            "Two modes:\n"
            "  color — HSL-blend the given RGB into the region; alpha set to 255.\n"
            "  alpha — adjust alpha only: 0=erase to transparent, 255=restore opacity."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "seed_x":       {"type": "integer", "description": "X coordinate of the seed pixel."},
                "seed_y":       {"type": "integer", "description": "Y coordinate of the seed pixel."},
                "mode":         {"type": "string", "enum": ["color", "alpha"],
                                 "description": "Fill mode: 'color' or 'alpha'. Default: 'color'."},
                "red":          {"type": "integer", "description": "Red (0-255). Required for mode=color."},
                "green":        {"type": "integer", "description": "Green (0-255). Required for mode=color."},
                "blue":         {"type": "integer", "description": "Blue (0-255). Required for mode=color."},
                "alpha":        {"type": "integer",
                                 "description": "Target alpha (0-255). Used for mode=alpha."},
                "black_thresh": {"type": "integer",
                                 "description": "max(R,G,B) below this = ink. Default: 64."},
                "tolerance":    {"type": "integer",
                                 "description": (
                                     "L∞ color distance; only fill pixels whose color is within "
                                     "this distance of the seed in any RGB channel (default: 128). "
                                     "Lower values stay closer to the seed color; use 255 to fill "
                                     "the full ink-bounded region regardless of color."
                                 )},
            },
            "required": ["seed_x", "seed_y"],
        }

    def execute(self, workspace: Workspace, *, seed_x: int, seed_y: int,
                mode: str = "color",
                red: int = 0, green: int = 0, blue: int = 0,
                alpha: int = 0,
                black_thresh: int = _BLACK_THRESH,
                tolerance: int | None = None) -> str:
        doc = workspace.active_document
        if doc is None or doc.image is None:
            return "Error: no active image."
        h, w = doc.image.shape[:2]
        if not (0 <= seed_x < w and 0 <= seed_y < h):
            return f"Error: seed ({seed_x},{seed_y}) out of bounds for {w}x{h} image."
        if mode not in ("color", "alpha"):
            return f"Error: mode must be 'color' or 'alpha', got {mode!r}."

        fill_color = (red, green, blue, alpha)
        result, count, used_tol = _flood_fill(doc.image, seed_x, seed_y, fill_color, mode, black_thresh, tolerance)
        idx = doc.push(result, reason=workspace.agent_reason
                       or f"fill({mode}) at ({seed_x},{seed_y})")
        tol_note = ""
        if used_tol is not None:
            if tolerance is None:
                tol_note = f" Auto-tolerance={used_tol} applied."
            else:
                tol_note = f" Tolerance={used_tol} applied."
        if mode == "color":
            return (f"Filled {count:,} pixels at ({seed_x},{seed_y}) with color "
                    f"({red},{green},{blue}), alpha=255.{tol_note} Version index: {idx}.")
        return (f"Set alpha={alpha} on {count:,} pixels at ({seed_x},{seed_y}).{tol_note} "
                f"Version index: {idx}.")


# ── demo ──────────────────────────────────────────────────────────────────────

def _make_checkerboard(width: int, height: int, size: int = 16) -> PILImage.Image:
    xs = np.arange(width) // size
    ys = np.arange(height) // size
    dark = ((xs[np.newaxis, :] + ys[:, np.newaxis]) % 2).astype(bool)
    arr = np.empty((height, width, 4), dtype=np.uint8)
    arr[~dark] = [204, 204, 204, 255]
    arr[ dark] = [153, 153, 153, 255]
    return PILImage.fromarray(arr, "RGBA")


def demo() -> None:
    import raylib as rl

    img_path = Path(__file__).parent.parent.parent / "test_images" / "bear_chef.png"
    orig = np.array(PILImage.open(img_path).convert("RGBA"))

    # Find a dark pixel to use as the dark-seed demo (first ink pixel found)
    dark_ys, dark_xs = np.where(orig[:, :, :3].max(axis=2) < _BLACK_THRESH)
    dark_sx, dark_sy = int(dark_xs[len(dark_xs) // 2]), int(dark_ys[len(dark_ys) // 2])
    print(f"Light-seed demo: alpha erase at (500, 75)")
    print(f"Dark-seed  demo: color fill (light blue) at ({dark_sx}, {dark_sy})")

    light_result, lc = _flood_fill(orig, 500, 75, fill_color=(0, 0, 0, 0), mode="alpha")
    dark_result,  dc = _flood_fill(orig, dark_sx, dark_sy,
                                   fill_color=(173, 216, 230, 255), mode="color")
    print(f"Light fill: {lc:,} pixels  |  Dark fill: {dc:,} pixels")

    DISP = 512
    checker = _make_checkerboard(DISP, DISP, size=16)

    def _prep_light(arr):
        pil = PILImage.fromarray(arr, "RGBA").resize((DISP, DISP), PILImage.LANCZOS)
        return PILImage.alpha_composite(checker, pil)

    orig_pil        = PILImage.fromarray(orig,         "RGBA").resize((DISP, DISP), PILImage.LANCZOS)
    light_composite = _prep_light(light_result)
    dark_pil        = PILImage.fromarray(dark_result,  "RGBA").resize((DISP, DISP), PILImage.LANCZOS)

    rl.InitWindow(DISP * 3, DISP, b"Fill Demo - ESC to quit")
    rl.SetTargetFPS(60)

    def _to_tex(img: PILImage.Image):
        rgba = img.convert("RGBA")
        w, h = rgba.size
        buf = rl.ffi.new("unsigned char[]", rgba.tobytes())
        rl_img = rl.ffi.new("Image *", {
            "data": buf, "width": w, "height": h,
            "mipmaps": 1, "format": rl.PIXELFORMAT_UNCOMPRESSED_R8G8B8A8,
        })
        return rl.LoadTextureFromImage(rl_img[0])

    orig_tex  = _to_tex(orig_pil)
    light_tex = _to_tex(light_composite)
    dark_tex  = _to_tex(dark_pil)

    WHITE = (255, 255, 255, 255)
    LABEL = (255, 255, 100, 255)

    while not rl.WindowShouldClose():
        rl.BeginDrawing()
        rl.ClearBackground((30, 30, 30, 255))
        rl.DrawTexture(orig_tex,  0,          0, WHITE)
        rl.DrawTexture(light_tex, DISP,       0, WHITE)
        rl.DrawTexture(dark_tex,  DISP * 2,   0, WHITE)
        rl.DrawText(b"Original",              10,            10, 18, LABEL)
        rl.DrawText(b"Light seed: erase bg",  DISP + 10,    10, 18, LABEL)
        rl.DrawText(b"Dark seed: recolor ink",DISP * 2 + 10, 10, 18, LABEL)
        rl.EndDrawing()

    rl.UnloadTexture(orig_tex)
    rl.UnloadTexture(light_tex)
    rl.UnloadTexture(dark_tex)
    rl.CloseWindow()


if __name__ == "__main__":
    demo()
