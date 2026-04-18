"""
Lightweight inline-markdown parser and styled text renderer.

Supported spans: **bold**, *italic*, ***bold-italic***, `code`
and underscore variants: __bold__, _italic_, ___bold-italic___

Newlines in runs are treated as explicit line breaks during wrapping.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentcore.font import Font

_CODE_COLOR = (200, 160, 80, 255)


# ---------------------------------------------------------------------------
# Style and Run
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Style:
    bold:   bool = False
    italic: bool = False
    code:   bool = False


NORMAL  = Style()
BOLD    = Style(bold=True)
ITALIC  = Style(italic=True)
BOLD_IT = Style(bold=True, italic=True)
CODE    = Style(code=True)


@dataclass
class Run:
    text:  str
    style: Style = field(default_factory=lambda: NORMAL)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

# Groups (1-indexed): code, bold-italic(*), bold(*), italic(*),
#                     bold-italic(_), bold(_), italic(_)
_PATTERN = re.compile(
    r'`([^`\n]+)`'
    r'|\*\*\*(.+?)\*\*\*'
    r'|\*\*(.+?)\*\*'
    r'|\*(.+?)\*'
    r'|___(.+?)___'
    r'|__(.+?)__'
    r'|_([^_\n]+)_'
)

_GROUP_STYLES = [CODE, BOLD_IT, BOLD, ITALIC, BOLD_IT, BOLD, ITALIC]


def parse(text: str) -> list[Run]:
    """Parse inline markdown in *text* and return a list of styled Runs."""
    runs: list[Run] = []
    pos = 0
    for m in _PATTERN.finditer(text):
        if m.start() > pos:
            runs.append(Run(text[pos:m.start()]))
        for g, style in enumerate(_GROUP_STYLES, start=1):
            if m.group(g) is not None:
                runs.append(Run(m.group(g), style))
                break
        pos = m.end()
    if pos < len(text):
        runs.append(Run(text[pos:]))
    return runs or [Run(text)]


# ---------------------------------------------------------------------------
# Word-wrap
# ---------------------------------------------------------------------------

def _get_font(style: Style, font_map: dict[Style, Font]) -> Font:
    return font_map.get(style, font_map[NORMAL])


def _tokenize(runs: list[Run]) -> list[tuple[str, Style]]:
    """Flatten runs into (word, style) tokens; '\n' signals an explicit line break."""
    tokens: list[tuple[str, Style]] = []
    for run in runs:
        paragraphs = run.text.split('\n')
        for i, para in enumerate(paragraphs):
            if i > 0:
                tokens.append(('\n', run.style))
            for word in para.split():
                tokens.append((word, run.style))
    return tokens


def _merge_line(tokens: list[tuple[str, Style]]) -> list[Run]:
    """Merge adjacent same-style words back into Runs (spaces baked in)."""
    if not tokens:
        return [Run('')]
    runs: list[Run] = []
    cur_words = [tokens[0][0]]
    cur_style = tokens[0][1]
    for word, style in tokens[1:]:
        if style == cur_style:
            cur_words.append(word)
        else:
            # trailing space keeps correct spacing across style boundaries
            runs.append(Run(' '.join(cur_words) + ' ', cur_style))
            cur_words = [word]
            cur_style = style
    runs.append(Run(' '.join(cur_words), cur_style))
    return runs


def _measure_line(tokens: list[tuple[str, Style]], font_size: float,
                  font_map: dict[Style, Font]) -> float:
    """Measure tokens exactly as draw_runs would render them."""
    total = 0.0
    for run in _merge_line(tokens):
        w, _ = _get_font(run.style, font_map).measure(run.text, font_size)
        total += w
    return total


def wrap_runs(
    runs: list[Run],
    max_width: float,
    font_size: float,
    font_map: dict[Style, Font],
) -> list[list[Run]]:
    """Word-wrap *runs* to *max_width* logical px. Returns a list of lines."""
    tokens = _tokenize(runs)

    lines: list[list[Run]] = []
    line_tokens: list[tuple[str, Style]] = []

    for word, style in tokens:
        if word == '\n':
            lines.append(_merge_line(line_tokens))
            line_tokens = []
            continue
        candidate = line_tokens + [(word, style)]
        if line_tokens and _measure_line(candidate, font_size, font_map) > max_width:
            lines.append(_merge_line(line_tokens))
            line_tokens = [(word, style)]
        else:
            line_tokens = candidate

    lines.append(_merge_line(line_tokens))
    return lines or [[Run('')]]


# ---------------------------------------------------------------------------
# Draw
# ---------------------------------------------------------------------------

def draw_runs(
    runs: list[Run],
    x: float,
    y: float,
    font_size: float,
    default_color: object,
    font_map: dict[Style, Font],
) -> None:
    """Draw *runs* as a single pre-wrapped line starting at (x, y)."""
    cx = x
    for run in runs:
        if not run.text:
            continue
        font = _get_font(run.style, font_map)
        color = _CODE_COLOR if run.style.code else default_color
        font.draw(run.text, cx, y, font_size, color)
        w, _ = font.measure(run.text, font_size)
        cx += w
