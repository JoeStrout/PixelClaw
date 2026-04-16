import raylib as rl

from .workspace import ImageWorkspace


def draw(workspace: ImageWorkspace) -> None:
    """Render the active image and any overlay (selection, etc.)."""
    doc = workspace.active_document
    if doc is None or doc.image is None:
        _draw_empty()
        return

    # TODO: convert PIL image to a raylib texture and blit it
    _draw_placeholder(doc.name)


def _draw_empty() -> None:
    text = b"No image open"
    rl.DrawText(text, 20, 20, 20, rl.GRAY)


def _draw_placeholder(name: str) -> None:
    text = f"[image: {name}]".encode()
    rl.DrawText(text, 20, 20, 20, rl.WHITE)
