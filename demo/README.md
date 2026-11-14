# Demo assets

The README GIF/MP4 and the `assets/` files are generated here.

- `demo-content.py` — prints the token-rich CI log shown in the demo pane
- `warm-session.py` — creates and prepares the `fingers-demo` Herdr session
- `fingers-demo.tape` — [VHS](https://github.com/charmbracelet/vhs) tape that
  attaches to the warm session and records the walkthrough

## Re-record

From the repository root:

```sh
herdr session stop fingers-demo 2>/dev/null; herdr session delete fingers-demo 2>/dev/null
python3 demo/warm-session.py
env -u HERDR_ENV -u HERDR_SOCKET_PATH -u HERDR_TAB_ID \
    -u HERDR_WORKSPACE_ID -u HERDR_PANE_ID -u HERDR_BIN_PATH \
    vhs demo/fingers-demo.tape
```

The raw recording contains brief blank frames while the overlay redraws.
Trim them and rebuild the outputs (this also produces the still):

```sh
ffmpeg -i assets/fingers-demo.mp4 -vf fps=10 /tmp/f10/f%03d.png
# drop the blank frames, then reassemble at 10 fps and regenerate the gif
# and still (see git history of assets/ for the exact frame numbers)
```

## Gotchas learned the hard way

- **Strip `HERDR_*` env vars** when invoking vhs from inside Herdr, or the
  nested client refuses to start ("nested herdr is disabled").
- **Warm the session first.** A fresh session runs the interactive shell
  init once; typing into that dialog races the recording. `warm-session.py`
  waits for the prompt, drops into `zsh -f`, seeds a harmless clipboard
  (`demo`), clears, and prints the demo content.
- **`Alt+g` in VHS is unreliable in headless Chrome** (only the bare `g`
  arrives). `Escape` followed by `Type@1ms "g"` sends a real `ESC g`.
- VHS needs a working `chromium` on `PATH`; a stale wrapper script pointing
  at a removed Chromium.app fails silently (no output files).
