"""Local, copy-only hint picker for Herdr. Python standard library only."""

import base64
import curses
import hashlib
import itertools
import json
import locale
import os
import re
import socket
import sys
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from ansi import Palette, Style, parse_lines

PLUGIN_ID = "thethoughtagen.herdr-fingers"
GEOMETRY_ENV = "LOCAL_FINGERS_GEOMETRY"
ALPHABET = "asdfghjklqwertyuiopzxcvbnm"
MAX_RESPONSE = 8 * 1024 * 1024
# URL alternatives come first so paths and numbers inside them aren't separate hits.
TOKEN = re.compile(
    r"https?://[^\s<>\"'`]+"
    r"|(?<![\w/])(?:~?/|\.{1,2}/)[^\s<>\"'`|]+"
    r"|(?<![\w/])(?:[\w@.-]+/)+[\w@.+:-]+"
    r"|\b[\w@-]+\.(?:[A-Za-z][A-Za-z0-9]{0,9})(?::\d+(?::\d+)?)?\b"
    r"|\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    r"|\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b"
    r"|\b(?:0x[0-9a-fA-F]+|[0-9a-fA-F]{7,40})\b"
    r"|\b[A-Z][A-Z0-9]+-\d+\b"
)


@dataclass(frozen=True)
class Span:
    row: int
    column: int
    text: str


@dataclass(frozen=True)
class Target:
    row: int
    column: int
    text: str
    hint: str
    spans: tuple[Span, ...] = ()


def cell_width(text):
    return sum(
        0
        if unicodedata.combining(ch)
        else 2
        if unicodedata.east_asian_width(ch) in "WF"
        else 1
        for ch in text
    )


def clean_line(text):
    # Never replay terminal escapes or invisible formatting controls from pane output.
    return "".join(ch if ch.isprintable() else " " for ch in text.expandtabs(8))


def hint_labels(count):
    size = 1
    while len(ALPHABET) ** size < count:
        size += 1
    return [
        "".join(chars)
        for chars in itertools.islice(itertools.product(ALPHABET, repeat=size), count)
    ]


def extract_targets(lines, wrap_width=None):
    # Herdr's layout rectangle can include a few border/scrollbar columns.
    # Use the observed right edge when it is close to the declared pane width.
    observed_width = max((cell_width(line.rstrip()) for line in lines), default=0)
    if wrap_width and wrap_width - 4 <= observed_width <= wrap_width:
        wrap_width = observed_width
    matches = []
    consumed = {}
    for row, line in enumerate(lines):
        for match in TOKEN.finditer(line):
            if match.start() < consumed.get(row, 0):
                continue
            raw = match.group()
            spans = [Span(row, cell_width(line[: match.start()]), raw)]
            end_row, end_index = row, match.end()
            # Only path/URL tokens can continue across a filled terminal row.
            while wrap_width and "/" in raw and end_row + 1 < len(lines):
                current = lines[end_row]
                if (
                    end_index != len(current.rstrip())
                    or cell_width(current.rstrip()) < wrap_width
                ):
                    break
                following = lines[end_row + 1]
                continuation = re.match(r"[ \t]*([^\s<>\"'`|]+)", following)
                if not continuation:
                    break
                chunk = continuation.group(1)
                # A new rooted path/URL is a separate item, not a continuation.
                if re.match(r"(?:/|~/|\.{1,2}/|https?://)", chunk):
                    break
                if not re.match(r"[\w@.%+~/-]", chunk):
                    break
                end_row += 1
                end_index = continuation.end(1)
                consumed[end_row] = end_index
                spans.append(
                    Span(end_row, cell_width(following[: continuation.start(1)]), chunk)
                )
                raw += chunk
            text = raw.rstrip(".,;!?)\u005d}")
            if not text:
                continue
            # Remove sentence punctuation from the final visible span too.
            trim = len(raw) - len(text)
            if trim:
                last = spans[-1]
                spans[-1] = Span(last.row, last.column, last.text[:-trim])
            matches.append((row, spans[0].column, text, tuple(spans)))
    values = dict.fromkeys(text for _, _, text, _ in matches)
    labels = dict(zip(values, hint_labels(len(values))))
    return [
        Target(row, column, text, labels[text], spans)
        for row, column, text, spans in matches
    ]


class Client:
    def __init__(self, path):
        self.path = path
        self.sequence = 0

    def call(self, method, params):
        # There is deliberately no API for sending text or running commands in a pane.
        if method not in {
            "pane.layout",
            "pane.read",
            "plugin.pane.open",
            "plugin.pane.close",
            "pane.zoom",
        }:
            raise ValueError("Unsupported API method")
        self.sequence += 1
        request = {"id": str(self.sequence), "method": method, "params": params}
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(5)
            connection.connect(self.path)
            connection.sendall(json.dumps(request).encode() + b"\n")
            with connection.makefile("rb") as stream:
                response = stream.readline(MAX_RESPONSE + 1)
        if len(response) > MAX_RESPONSE or not response.endswith(b"\n"):
            raise ValueError("Invalid or oversized Herdr response")
        envelope = json.loads(response)
        if envelope.get("id") != request["id"]:
            raise ValueError("Mismatched Herdr response")
        if "error" in envelope:
            # Don't log response bodies: they could contain terminal secrets.
            raise RuntimeError("Herdr API request failed")
        return envelope["result"]


def source_geometry(layout, pane_id):
    pane = next(pane for pane in layout["panes"] if pane["pane_id"] == pane_id)
    area = layout["area"]
    rect = area if layout.get("zoomed") else pane["rect"]
    return {
        "pane_id": pane_id,
        "x": rect["x"] - area["x"],
        "y": rect["y"] - area["y"],
        "width": rect["width"],
        "height": rect["height"],
        "area_width": area["width"],
        "area_height": area["height"],
    }


def fit_geometry(geometry, size):
    height, width = size
    area_width = geometry.get("area_width", width)
    area_height = geometry.get("area_height", height)
    x = round(geometry["x"] * width / area_width)
    y = round(geometry["y"] * height / area_height)
    right = round((geometry["x"] + geometry["width"]) * width / area_width)
    bottom = round(
        (geometry["y"] + geometry.get("height", height)) * height / area_height
    )
    return {**geometry, "x": x, "y": y, "width": right - x, "height": bottom - y}


def open_picker(client, pane_id):
    layout = client.call("pane.layout", {"pane_id": pane_id})["layout"]
    geometry = source_geometry(layout, pane_id)
    geometry["panes"] = [
        source_geometry(layout, pane["pane_id"])
        for pane in layout["panes"]
        if not layout.get("zoomed") or pane["pane_id"] == pane_id
    ]
    result = client.call(
        "plugin.pane.open",
        {
            "plugin_id": PLUGIN_ID,
            "entrypoint": "picker",
            "env": {GEOMETRY_ENV: json.dumps(geometry)},
        },
    )
    overlay_id = result["plugin_pane"]["pane"]["pane_id"]
    client.call("pane.zoom", {"pane_id": overlay_id, "mode": "on"})
    return overlay_id


def toggle_picker(client, pane_id, state_dir):
    # Keep only an opaque pane ID, scoped to this server. Never persist pane text.
    server = hashlib.sha256(os.fsencode(client.path)).hexdigest()[:24]
    marker = Path(state_dir) / f"fingers-overlay-{server}"
    try:
        descriptor = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor) as stream:
            overlay_id = stream.read(256).strip()
    except FileNotFoundError:
        overlay_id = None
    if pane_id == overlay_id:
        client.call("plugin.pane.close", {"pane_id": overlay_id})
        marker.unlink(missing_ok=True)
        return
    overlay_id = open_picker(client, pane_id)
    marker.parent.mkdir(parents=True, exist_ok=True)
    # Private, atomic replacement: never follow a pre-existing marker symlink.
    with tempfile.NamedTemporaryFile(
        mode="w", dir=marker.parent, prefix=".fingers-", delete=False
    ) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(overlay_id)
            stream.flush()
            os.replace(temporary, marker)
        finally:
            temporary.unlink(missing_ok=True)
    return overlay_id


def draw_text(screen, row, column, text, style=0, limit=None):
    height, width = screen.getmaxyx()
    if row < 0 or row >= height or column < 0 or column >= width:
        return
    available = width - column
    if limit is not None:
        available = min(available, limit)
    clipped = []
    used = 0
    for ch in text:
        size = cell_width(ch)
        if used + size > available:
            break
        clipped.append(ch)
        used += size
    try:
        screen.addstr(row, column, "".join(clipped), style)
    except curses.error:
        # Curses reports an error after writing the bottom-right cell.
        pass


def settle_terminal(screen):
    # Opening/zooming a Herdr overlay can briefly give it the source pane's
    # dimensions. Let the initial PTY resize finish before pinning the snapshot.
    screen.timeout(150)
    deadline = time.monotonic() + 1
    try:
        while time.monotonic() < deadline:
            try:
                key = screen.get_wch()
            except curses.error:
                break
            if key != curses.KEY_RESIZE:
                curses.unget_wch(key)
                break
    finally:
        screen.timeout(-1)


def draw_pane(screen, lines, geometry, styles, palette):
    height, width = screen.getmaxyx()
    x, y = geometry["x"], geometry["y"]
    pane_width = min(geometry["width"], width - x)
    for row, line in enumerate(lines[: geometry["height"]]):
        if y + row >= height - 1:
            break
        if styles is None:
            draw_text(screen, y + row, x, line, limit=pane_width)
        else:
            column = 0
            for style, group in itertools.groupby(
                zip(line, styles[row]), key=lambda item: item[1]
            ):
                chunk = "".join(char for char, _ in group)
                draw_text(
                    screen,
                    y + row,
                    x + column,
                    chunk,
                    palette.attribute(style),
                    pane_width - column,
                )
                column += cell_width(chunk)


def picker(screen, lines, geometry, styles=None, backdrop=()):
    # Curses otherwise waits up to a second to distinguish Esc from Alt/arrow
    # sequences. This picker uses plain letters, so prefer immediate cancellation.
    curses.set_escdelay(25)
    curses.curs_set(0)
    settle_terminal(screen)
    screen.keypad(True)
    palette = Palette()
    hint_style = palette.attribute(Style(fg=0, bg=11, attrs=curses.A_BOLD))
    initial_size = screen.getmaxyx()
    height, width = initial_size
    snapshot_width = geometry["width"]
    geometry = fit_geometry(geometry, initial_size)
    backdrop = [
        (fit_geometry(rect, initial_size), text, colors)
        for rect, text, colors in backdrop
    ]
    x, y = geometry["x"], geometry["y"]
    pane_width = min(geometry["width"], width - x)
    # Reserve the final overlay row for controls; never hint hidden text.
    targets = [
        target
        for target in extract_targets(lines, wrap_width=snapshot_width)
        if target.row < geometry["height"]
        and y + target.row < height - 1
        and target.column + len(target.hint) <= pane_width
    ]
    prefix = ""
    while True:
        screen.erase()
        for rect, text, colors in backdrop:
            draw_pane(screen, text, rect, colors, palette)
        draw_pane(screen, lines, geometry, styles, palette)
        candidates = [target for target in targets if target.hint.startswith(prefix)]
        if styles is None:
            for target in candidates:
                for span in target.spans:
                    if span.row < geometry["height"] and y + span.row < height - 1:
                        draw_text(
                            screen,
                            y + span.row,
                            x + span.column,
                            span.text,
                            curses.A_BOLD,
                            pane_width - span.column,
                        )
        # Paint hints last so match text can't cover an adjacent hint.
        for target in candidates:
            draw_text(
                screen,
                y + target.row,
                x + target.column,
                target.hint,
                hint_style,
            )
        count = len({target.hint for target in candidates})
        status = f" Fingers: {count} targets | type hint to copy | Alt+g/Esc cancel | {prefix}"
        draw_text(screen, height - 1, 0, status, curses.A_REVERSE)
        screen.refresh()
        key = screen.get_wch()
        if key in ("\x1b", "\x03") or screen.getmaxyx() != initial_size:
            return None
        if key == curses.KEY_RESIZE:
            # Herdr sends a startup resize notification when zooming the overlay,
            # even when its dimensions haven't changed. That isn't user cancel.
            continue
        if key in (curses.KEY_BACKSPACE, "\x7f", "\b"):
            prefix = prefix[:-1]
        elif isinstance(key, str) and key.lower() in ALPHABET:
            attempt = prefix + key.lower()
            matching = [
                target for target in candidates if target.hint.startswith(attempt)
            ]
            if matching:
                prefix = attempt
                if matching[0].hint == prefix:
                    return matching[0].text
            else:
                curses.beep()


def clipboard_sequence(text):
    # Base64 prevents copied data from injecting OSC/terminal control sequences.
    encoded = base64.b64encode(text.encode()).decode("ascii")
    return f"\x1b]52;c;{encoded}\x07"


def main():
    if os.environ.get("HERDR_ENV") != "1":
        raise RuntimeError("Run through the Herdr plugin action")
    client = Client(os.environ["HERDR_SOCKET_PATH"])
    context = json.loads(os.environ["HERDR_PLUGIN_CONTEXT_JSON"])
    if sys.argv[1:] == ["open"]:
        toggle_picker(
            client, context["focused_pane_id"], os.environ["HERDR_PLUGIN_STATE_DIR"]
        )
        return
    geometry = json.loads(os.environ[GEOMETRY_ENV])

    def read_snapshot(rect):
        result = client.call(
            "pane.read",
            {
                "pane_id": rect["pane_id"],
                "source": "visible",
                "format": "ansi",
                "strip_ansi": False,
            },
        )
        lines, styles = parse_lines(result["read"]["text"])
        return lines[: rect["height"]], styles[: rect["height"]]

    lines, styles = read_snapshot(geometry)
    backdrop = []
    for rect in geometry.get("panes", []):
        if rect["pane_id"] == geometry["pane_id"]:
            continue
        try:
            text, colors = read_snapshot(rect)
        except RuntimeError:
            # A neighboring pane can close between opening and rendering.
            continue
        backdrop.append((rect, text, colors))
    locale.setlocale(locale.LC_ALL, "")
    copied = curses.wrapper(picker, lines, geometry, styles, backdrop)
    if copied is not None:
        sys.stdout.write(clipboard_sequence(copied))
        sys.stdout.flush()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, KeyError, StopIteration, RuntimeError, curses.error):
        print(
            "Fingers could not open. Check the plugin context and Herdr connection.",
            file=sys.stderr,
        )
        sys.exit(1)
