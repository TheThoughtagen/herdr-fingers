Output assets/fingers-demo.gif
Output assets/fingers-demo.mp4

Set Shell "zsh"
Set FontSize 15
Set Width 1200
Set Height 640
Set TypingSpeed 120ms
Set Framerate 20
Set CursorBlink false

# -- Attach to the pre-warmed demo session (see demo/README) ----------------
Hide
Type@60ms "herdr --session fingers-demo"
Enter
Sleep 4s
Show

# -- Beat 1: open the picker (Alt+g = ESC+g) --------------------------------
Sleep 1s
Escape
Type@1ms "g"
Sleep 2.8s

# -- Beat 2: type the hint over the docs URL to copy it ---------------------
Type "g"
Sleep 800ms

# -- Beat 3: prove the copy with pbpaste ------------------------------------
Type "pbpaste; echo"
Enter
Sleep 1.8s

# -- Beat 4: reopen, cancel with Esc ----------------------------------------
Escape
Type@1ms "g"
Sleep 1.8s
Escape
Sleep 1.2s
