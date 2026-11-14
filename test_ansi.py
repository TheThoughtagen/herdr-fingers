import curses
import unittest
from unittest.mock import patch

from ansi import Palette, Style, indexed_rgb, parse_lines


class AnsiTests(unittest.TestCase):
    def test_preserves_plain_text_and_styles(self):
        lines, styles = parse_lines("before \x1b[31;1mred\x1b[0m after")
        self.assertEqual(lines, ["before red after"])
        self.assertEqual(styles[0][7], Style(fg=1, attrs=curses.A_BOLD))
        self.assertEqual(styles[0][-1], Style())

    def test_extended_colors_and_background(self):
        lines, styles = parse_lines("\x1b[38;5;120;48;5;23mfoo\x1b[39;49m!")
        self.assertEqual(lines, ["foo!"])
        self.assertEqual(styles[0][0], Style(fg=120, bg=23))
        self.assertEqual(styles[0][-1], Style())

    def test_rgb_uses_palette_without_modifying_terminal_colors(self):
        _, styles = parse_lines("\x1b[38;2;255;0;0mred")
        self.assertEqual(styles[0][0].fg, 196)
        self.assertEqual(indexed_rgb(128, 128, 128), 244)

    def test_strips_osc_clipboard_links_and_other_control_codes(self):
        lines, _ = parse_lines(
            "\x1b]52;c;evil\x07a\x1b[2Jb\x1b]8;;https://example.com\x1b\\c\x1b]8;;\x1b\\"
        )
        self.assertEqual(lines, ["abc"])

    def test_no_controls_replayed(self):
        lines, _ = parse_lines("a\x00\x07\u202eb")
        self.assertTrue(all(char.isprintable() for char in lines[0]))

    def test_style_carries_across_rows(self):
        lines, styles = parse_lines("\x1b[92mgreen\nstill green\x1b[0m\nnormal")
        self.assertEqual(len(lines), 3)
        self.assertEqual(styles[1][0].fg, 10)
        self.assertEqual(styles[2][0], Style())

    def test_tabs_and_plain_text_have_matching_style_lengths(self):
        lines, styles = parse_lines("a\tb\r\nfoo")
        self.assertEqual(lines, ["a       b", "foo"])
        self.assertEqual([len(row) for row in styles], [len(line) for line in lines])

    def test_attribute_resets(self):
        _, styles = parse_lines("\x1b[1;4;7mA\x1b[22;24;27mB")
        self.assertEqual(
            styles[0][0].attrs, curses.A_BOLD | curses.A_UNDERLINE | curses.A_REVERSE
        )
        self.assertEqual(styles[0][1], Style())

    def test_palette_uses_terminal_default_colors(self):
        with (
            patch("ansi.curses.has_colors", return_value=True),
            patch("ansi.curses.start_color"),
            patch("ansi.curses.use_default_colors") as defaults,
            patch("ansi.curses.COLORS", 256, create=True),
        ):
            palette = Palette()
            defaults.assert_called_once()
            self.assertEqual(palette.attribute(Style()), 0)


if __name__ == "__main__":
    unittest.main()
