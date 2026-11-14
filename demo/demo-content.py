#!/usr/bin/env python3
"""Print a realistic, token-rich CI log for the demo pane."""

GREEN = "\x1b[32m"
RED = "\x1b[31m"
CYAN = "\x1b[36m"
BLUE = "\x1b[34m\x1b[4m"
YELLOW = "\x1b[33m"
MAGENTA = "\x1b[35m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"
RESET = "\x1b[0m"

print(f"{DIM}$ {RESET}{BOLD}make check{RESET}  {DIM}(branch: main){RESET}")
print(f"{GREEN}ok  {RESET}unit tests {DIM}·{RESET} 34 passed {DIM}·{RESET} 0.84s")
print(f"{RED}FAIL{RESET} {CYAN}tests/test_fingers.py::test_hint_labels{RESET} row 12")
print(
    f'{DIM}  File "{CYAN}/Users/dev/src/herdr-fingers/fingers.py{RESET}", line 88{DIM}, in extract_targets{RESET}'
)
print(f"{DIM}  full traceback: {CYAN}/tmp/pytest-dev/f8a3c1d2/traceback.log{RESET}")
print()
print(f"{BOLD}next steps{RESET}")
print(f"  docs    {BLUE}https://herdr.dev/docs/plugins/fingers{RESET}")
print(
    f"  report  {BLUE}https://github.com/TheThoughtagen/herdr-fingers/issues/42{RESET}"
)
print(
    f"  bisect  {DIM}HEAD {YELLOW}9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0{RESET} still fails"
)
print(f"  flaky   {DIM}node-2 {YELLOW}10.0.4.13:9092{RESET} unreachable (3 attempts)")
print(f"  trace   request id {MAGENTA}3f2504e0-4f89-11d3-9a0c-0305e82c3301{RESET}")
print(f"  ticket  {MAGENTA}PROJ-1042{RESET} {DIM}owner @adent{RESET}")
