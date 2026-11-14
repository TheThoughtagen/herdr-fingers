# Herdr Fingers

Keyboard hints for copying paths, URLs, and identifiers from [Herdr](https://herdr.dev)
terminal panes. Inspired by tmux-fingers. Python standard library only; no runtime
packages, network calls, or automatic pasting.

## Requirements

- Herdr 0.9 or newer
- Python 3.10+ with curses
- macOS or Linux

## Install

```sh
herdr plugin install TheThoughtagen/herdr-fingers
```

Add this to `~/.config/herdr/config.toml`, choosing an unused key:

```toml
[[keys.command]]
key = "alt+g"
type = "plugin_action"
command = "thethoughtagen.herdr-fingers.open"
description = "copy visible token"
```

Apply it:

```sh
herdr config check
herdr server reload-config
```

## Use

1. Focus a pane and press **Alt+g**.
2. Type the letter label over a match to copy it immediately. No Enter needed.
3. Press **Alt+g** again, **Esc**, or **Ctrl-C** to cancel.

- More than 26 unique tokens use multi-letter hints.
- Backspace corrects a partially typed hint.
- Identical tokens share a hint. Uppercase letters also only copy.
- Matches include URLs, paths, filenames, IPv4 addresses, UUIDs, Git hashes,
  and ticket IDs.
- Long paths and URLs can continue across rows, including Claude's indented
  continuation rows. Copied values have no inserted newlines or indentation.

The overlay preserves source colors and redraws neighboring panes, but only the
focused pane gets hints. All panes continue running; the overlay is a snapshot,
not live output. Closing it restores the previous layout and zoom. Resizing cancels
it. Escape uses a 25ms delay.

## Safety

- No runtime packages, network clients, subprocesses, telemetry, or startup hooks.
- Uses Herdr's local Unix socket. No send-text or command-execution API.
- Clipboard writes use base64-encoded OSC 52, supported by Herdr.
- No terminal text is saved to disk, passed in environment variables, or logged.
- Only a server-scoped overlay pane ID is saved in the plugin state directory for
  toggling. Marker files are private and reject symlinks.
- Only source color/attribute escapes are parsed; other terminal control
  sequences are discarded, never replayed.
- No automatic pasting, URL opening, or executing selected text.

This runs as your user, not in a sandbox. Clipboard history or sync can retain
copied secrets.

## Limitations

- Herdr overlays technically zoom the tab; the plugin reconstructs the original
  pane regions to preserve context. Other panes are snapshots while it is open.
- Wrap detection is heuristic because the API does not expose per-row wrap
  metadata here. Short hard-break lines and newly rooted paths are not joined.
  Offscreen or application-truncated suffixes cannot be recovered.
- Truecolor is approximated to the terminal's 256-color palette.
- Trailing sentence punctuation is trimmed heuristically.
- Complex emoji/Unicode graphemes may not align perfectly.
- The final overlay row is reserved for controls.
- Hint labels can obscure nearby text; Esc returns to the original pane.

## Development

```sh
git clone https://github.com/TheThoughtagen/herdr-fingers.git
cd herdr-fingers
herdr plugin link "$PWD"
```

Runtime and unit tests need only Python's standard library:

```sh
python3 -m unittest -v
```

Formatting and linting use [uv](https://docs.astral.sh/uv/) and Ruff. Fetch Ruff once,
then the Make targets run offline:

```sh
uvx ruff --version
make format
make check
```

`make check` runs unit tests, Ruff lint, and bytecode compilation.

## Remove

Remove the binding from your Herdr config, then:

```sh
herdr plugin uninstall thethoughtagen.herdr-fingers
herdr server reload-config
```

For a locally linked checkout, use `herdr plugin unlink` instead of `uninstall`.
