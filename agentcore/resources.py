"""
Shared resource accessors for agentcore.

Usage:
    from agentcore.resources import default_font
    default_font().draw("Hello", 10, 10, 14, rl.WHITE)
"""

from pathlib import Path

from .font import Font

_RESOURCES = Path(__file__).parent / "resources"

_default_font: Font | None = None


def default_font() -> Font:
    """Return the shared default Font, creating it on first call."""
    global _default_font
    if _default_font is None:
        _default_font = Font(_RESOURCES / "DejaVuSans.ttf")
    return _default_font


def unload_all() -> None:
    """Unload all cached resources.  Call once before CloseWindow()."""
    global _default_font
    if _default_font is not None:
        _default_font.unload()
        _default_font = None
