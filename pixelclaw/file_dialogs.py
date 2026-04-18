"""
Native file dialogs for PixelClaw.

Platform support lives here so callers stay simple.
Add new platforms by implementing the same interface in a new branch of save_image().
"""

import sys
from pathlib import Path


def open_images() -> list[Path]:
    """Show a native open dialog for image files.

    Returns a list of chosen Paths, or an empty list if the user cancelled.
    """
    if sys.platform == "darwin":
        return _open_darwin()
    return _open_tkinter()


def save_image(default_name: str) -> Path | None:
    """Show a native save dialog for image files.

    default_name  — suggested filename; '.png' is appended if there is no extension.
    Returns the chosen Path, or None if the user cancelled.
    """
    p = Path(default_name)
    if not p.suffix:
        p = p.with_suffix(".png")

    if sys.platform == "darwin":
        return _save_darwin(p.name)

    # Fallback for other platforms (Linux, Windows) — add native impls here later
    return _save_tkinter(p.name)


# ---------------------------------------------------------------------------
# macOS — NSOpenPanel / NSSavePanel via PyObjC
# ---------------------------------------------------------------------------

_IMAGE_TYPES_DARWIN = ["png", "jpg", "jpeg", "webp", "bmp", "tiff", "tif"]


def _refocus_app() -> None:
    from AppKit import NSApp
    NSApp.activateIgnoringOtherApps_(True)


def _open_darwin() -> list[Path]:
    from AppKit import NSOpenPanel, NSModalResponseOK

    panel = NSOpenPanel.openPanel()
    panel.setTitle_("Open Image")
    panel.setAllowsMultipleSelection_(True)
    panel.setCanChooseFiles_(True)
    panel.setCanChooseDirectories_(False)
    panel.setAllowedFileTypes_(_IMAGE_TYPES_DARWIN)

    result = panel.runModal()
    _refocus_app()
    if result == NSModalResponseOK:
        return [Path(url.path()) for url in panel.URLs()]
    return []


def _save_darwin(default_name: str) -> Path | None:
    from AppKit import NSSavePanel, NSModalResponseOK

    panel = NSSavePanel.savePanel()
    panel.setTitle_("Save Image")
    panel.setNameFieldStringValue_(default_name)
    panel.setAllowedFileTypes_(_IMAGE_TYPES_DARWIN)
    panel.setAllowsOtherFileTypes_(True)
    panel.setExtensionHidden_(False)

    result = panel.runModal()
    _refocus_app()
    if result == NSModalResponseOK:
        return Path(panel.URL().path())
    return None


# ---------------------------------------------------------------------------
# Fallback — tkinter (non-macOS)
# ---------------------------------------------------------------------------

_IMAGE_FILETYPES_TK = [
    ("PNG image",  "*.png"),
    ("JPEG image", "*.jpg *.jpeg"),
    ("WebP image", "*.webp"),
    ("BMP image",  "*.bmp"),
    ("TIFF image", "*.tiff *.tif"),
    ("All files",  "*.*"),
]


def _open_tkinter() -> list[Path]:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    paths = filedialog.askopenfilenames(filetypes=_IMAGE_FILETYPES_TK)
    root.destroy()
    return [Path(p) for p in paths]


def _save_tkinter(default_name: str) -> Path | None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    path_str = filedialog.asksaveasfilename(
        initialfile=default_name,
        defaultextension=".png",
        filetypes=_IMAGE_FILETYPES_TK,
    )
    root.destroy()
    return Path(path_str) if path_str else None
