"""
Shared resource accessors for agentcore.

Usage:
    from agentcore.resources import default_font
    default_font().draw("Hello", 10, 10, 14, rl.WHITE)
"""

from pathlib import Path

from .font import Font

_RESOURCES = Path(__file__).parent / "resources"

_default_font:     Font | None = None
_bold_font:        Font | None = None
_italic_font:      Font | None = None
_bold_italic_font: Font | None = None

_font_map: dict | None = None


def default_font() -> Font:
    global _default_font
    if _default_font is None:
        _default_font = Font(_RESOURCES / "DejaVuSans.ttf")
    return _default_font


def bold_font() -> Font:
    global _bold_font
    if _bold_font is None:
        _bold_font = Font(_RESOURCES / "DejaVuSans-Bold.ttf")
    return _bold_font


def italic_font() -> Font:
    global _italic_font
    if _italic_font is None:
        _italic_font = Font(_RESOURCES / "DejaVuSans-Oblique.ttf")
    return _italic_font


def bold_italic_font() -> Font:
    global _bold_italic_font
    if _bold_italic_font is None:
        _bold_italic_font = Font(_RESOURCES / "DejaVuSans-BoldOblique.ttf")
    return _bold_italic_font


def style_font_map() -> dict:
    """Return a {Style: Font} mapping for use with mdrender.wrap_runs / draw_runs."""
    global _font_map
    if _font_map is None:
        from .mdrender import NORMAL, BOLD, ITALIC, BOLD_IT, CODE
        _font_map = {
            NORMAL:  default_font(),
            BOLD:    bold_font(),
            ITALIC:  italic_font(),
            BOLD_IT: bold_italic_font(),
            CODE:    default_font(),   # same font, different color via draw_runs
        }
    return _font_map


def unload_all() -> None:
    """Unload all cached resources. Call once before CloseWindow()."""
    global _default_font, _bold_font, _italic_font, _bold_italic_font, _font_map
    for f in (_default_font, _bold_font, _italic_font, _bold_italic_font):
        if f is not None:
            f.unload()
    _default_font     = None
    _bold_font        = None
    _italic_font      = None
    _bold_italic_font = None
    _font_map         = None
