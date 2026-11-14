"""Parse only SGR colors/attributes, never replay terminal control sequences."""

import curses
import re
from dataclasses import dataclass, replace

ESCAPE = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]"
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
    r"|\x1b[P_X^][\s\S]*?\x1b\\"
    r"|\x1b."
)


@dataclass(frozen=True)
class Style:
    fg: int = -1
    bg: int = -1
    attrs: int = 0


def indexed_rgb(red, green, blue):
    """Approximate truecolor with the nearest xterm cube or gray (no palette writes)."""
    levels = (0, 95, 135, 175, 215, 255)
    indices = [
        min(range(6), key=lambda i: abs(levels[i] - value))
        for value in (red, green, blue)
    ]
    cube = 16 + 36 * indices[0] + 6 * indices[1] + indices[2]
    cube_error = sum(
        (value - levels[i]) ** 2 for value, i in zip((red, green, blue), indices)
    )
    gray = min(
        range(24),
        key=lambda i: sum((value - (8 + i * 10)) ** 2 for value in (red, green, blue)),
    )
    gray_error = sum((value - (8 + gray * 10)) ** 2 for value in (red, green, blue))
    return 232 + gray if gray_error < cube_error else cube


def sgr(style, parameters):
    try:
        codes = [int(value) if value else 0 for value in parameters.split(";")]
    except ValueError:
        return style
    position = 0
    while position < len(codes):
        code = codes[position]
        position += 1
        if code == 0:
            style = Style()
        elif code in (1, 2, 3, 4, 7):
            flags = {
                1: curses.A_BOLD,
                2: curses.A_DIM,
                3: getattr(curses, "A_ITALIC", 0),
                4: curses.A_UNDERLINE,
                7: curses.A_REVERSE,
            }
            style = replace(style, attrs=style.attrs | flags[code])
        elif code in (22, 23, 24, 27):
            flags = {
                22: curses.A_BOLD | curses.A_DIM,
                23: getattr(curses, "A_ITALIC", 0),
                24: curses.A_UNDERLINE,
                27: curses.A_REVERSE,
            }
            style = replace(style, attrs=style.attrs & ~flags[code])
        elif 30 <= code <= 37:
            style = replace(style, fg=code - 30)
        elif 90 <= code <= 97:
            style = replace(style, fg=code - 90 + 8)
        elif 40 <= code <= 47:
            style = replace(style, bg=code - 40)
        elif 100 <= code <= 107:
            style = replace(style, bg=code - 100 + 8)
        elif code == 39:
            style = replace(style, fg=-1)
        elif code == 49:
            style = replace(style, bg=-1)
        elif code in (38, 48):
            remaining = codes[position:]
            color = None
            if len(remaining) >= 2 and remaining[0] == 5:
                color = max(0, min(255, remaining[1]))
                position += 2
            elif len(remaining) >= 4 and remaining[0] == 2:
                color = indexed_rgb(
                    *(max(0, min(255, value)) for value in remaining[1:4])
                )
                position += 4
            else:
                break
            style = replace(style, **{"fg" if code == 38 else "bg": color})
    return style


def parse_lines(text):
    """Return plain rows plus per-character styles; discard non-SGR escape codes."""
    rows = [[]]
    styles = [[]]
    style = Style()

    def append_plain(chunk):
        for char in chunk:
            if char == "\n":
                rows.append([])
                styles.append([])
            elif char == "\t":
                spaces = 8 - len(rows[-1]) % 8
                rows[-1].extend(" " * spaces)
                styles[-1].extend([style] * spaces)
            elif char != "\r":
                rows[-1].append(char if char.isprintable() else " ")
                styles[-1].append(style)

    end = 0
    for match in ESCAPE.finditer(text):
        append_plain(text[end : match.start()])
        escape = match.group()
        if escape.startswith("\x1b[") and escape.endswith("m"):
            style = sgr(style, escape[2:-1])
        end = match.end()
    append_plain(text[end:])
    return ["".join(row) for row in rows], styles


class Palette:
    def __init__(self):
        self.pairs = {}
        self.enabled = curses.has_colors()
        if self.enabled:
            curses.start_color()
            curses.use_default_colors()

    def attribute(self, style):
        if not self.enabled:
            return style.attrs
        fg = style.fg if style.fg < curses.COLORS else -1
        bg = style.bg if style.bg < curses.COLORS else -1
        if fg == bg == -1:
            return style.attrs
        key = (fg, bg)
        if key not in self.pairs:
            pair = len(self.pairs) + 1
            if pair >= curses.COLOR_PAIRS:
                return style.attrs
            curses.init_pair(pair, fg, bg)
            self.pairs[key] = pair
        return curses.color_pair(self.pairs[key]) | style.attrs
