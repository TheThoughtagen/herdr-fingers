import base64
import json
import tempfile
import unittest
from unittest.mock import Mock

import fingers


class FingersTests(unittest.TestCase):
    def setUp(self):
        palette = unittest.mock.patch.object(fingers, "Palette")
        palette.start().return_value.attribute.return_value = 0
        self.addCleanup(palette.stop)

    def values(self, text):
        return [target.text for target in fingers.extract_targets([text])]

    def test_common_tokens(self):
        text = "https://example.com/x /tmp/main.py ./src/a.ts src/lib.ts README.md"
        self.assertEqual(self.values(text), text.split())

    def test_identifiers(self):
        text = "192.168.1.20:8080 550e8400-e29b-41d4-a716-446655440000 deadbeef ENG-123"
        self.assertEqual(self.values(text), text.split())

    def test_url_is_not_split_into_nested_matches(self):
        self.assertEqual(
            self.values("https://example.com/a/deadbeef"),
            ["https://example.com/a/deadbeef"],
        )

    def test_trailing_punctuation(self):
        self.assertEqual(
            self.values("(https://example.com/a), /tmp/main.py."),
            ["https://example.com/a", "/tmp/main.py"],
        )

    def test_duplicates_share_hint(self):
        targets = fingers.extract_targets(["/tmp/a /tmp/a", "/tmp/b"])
        self.assertEqual(targets[0].hint, targets[1].hint)
        self.assertNotEqual(targets[0].hint, targets[2].hint)

    def test_labels_are_unique_and_prefix_free(self):
        for count in (0, 1, 26, 27, 676, 677):
            labels = fingers.hint_labels(count)
            self.assertEqual(len(set(labels)), count)
            self.assertLessEqual(len({len(label) for label in labels}), 1)

    def test_unicode_and_tab_columns(self):
        line = fingers.clean_line("界\t/tmp/a")
        target = fingers.extract_targets([line])[0]
        self.assertEqual(target.column, 9)

    def test_control_characters_removed(self):
        cleaned = fingers.clean_line("hello\x1b\x07\x00\u202eworld")
        self.assertTrue(all(ch.isprintable() for ch in cleaned))

    def test_clipboard_is_encoded_not_interpolated(self):
        text = "hello\x1b]52;c;evil\x07"
        sequence = fingers.clipboard_sequence(text)
        self.assertEqual(sequence.count("\x1b"), 1)
        self.assertEqual(sequence.count("\x07"), 1)
        self.assertEqual(base64.b64decode(sequence[7:-1]).decode(), text)

    def test_geometry_uses_source_region(self):
        layout = {
            "area": {"x": 5, "y": 2, "width": 100, "height": 40},
            "panes": [
                {
                    "pane_id": "test",
                    "rect": {"x": 55, "y": 2, "width": 50, "height": 40},
                }
            ],
        }
        geometry = fingers.source_geometry(layout, "test")
        self.assertEqual((geometry["x"], geometry["y"], geometry["width"]), (50, 0, 50))
        layout["zoomed"] = True
        geometry = fingers.source_geometry(layout, "test")
        self.assertEqual((geometry["x"], geometry["y"], geometry["width"]), (0, 0, 100))

    def test_launcher_passes_geometry_not_terminal_text(self):
        client = Mock()
        client.call.side_effect = [
            {
                "layout": {
                    "area": {"x": 0, "y": 0, "width": 80, "height": 24},
                    "panes": [
                        {
                            "pane_id": "source",
                            "rect": {"x": 0, "y": 0, "width": 80, "height": 24},
                        }
                    ],
                }
            },
            {"plugin_pane": {"pane": {"pane_id": "overlay"}}},
            {},
        ]
        fingers.open_picker(client, "source")
        calls = client.call.call_args_list
        self.assertEqual(
            [call.args[0] for call in calls],
            ["pane.layout", "plugin.pane.open", "pane.zoom"],
        )
        env = calls[1].args[1]["env"]
        self.assertEqual(json.loads(env[fingers.GEOMETRY_ENV])["pane_id"], "source")

    def test_send_text_api_is_not_available(self):
        with self.assertRaises(ValueError):
            fingers.Client("/unused").call("pane.send_text", {})

    def test_picker_selects_without_pasting(self):
        screen = Mock()
        screen.getmaxyx.return_value = (24, 80)
        screen.get_wch.return_value = "a"
        with (
            unittest.mock.patch.object(fingers.curses, "curs_set"),
            unittest.mock.patch.object(fingers, "settle_terminal"),
        ):
            selected = fingers.picker(screen, ["/tmp/a"], {"x": 0, "y": 0, "width": 80})
        self.assertEqual(selected, "/tmp/a")

    def test_picker_cancel_and_resize(self):
        for key in ("\x1b", "\x03"):
            screen = Mock()
            screen.getmaxyx.return_value = (24, 80)
            screen.get_wch.return_value = key
            with (
                unittest.mock.patch.object(fingers.curses, "curs_set"),
                unittest.mock.patch.object(fingers.curses, "set_escdelay") as delay,
                unittest.mock.patch.object(fingers, "settle_terminal"),
            ):
                self.assertIsNone(
                    fingers.picker(screen, ["/tmp/a"], {"x": 0, "y": 0, "width": 80})
                )
                delay.assert_called_once_with(25)

    def test_same_size_resize_does_not_close_picker(self):
        screen = Mock()
        screen.getmaxyx.return_value = (24, 80)
        screen.get_wch.side_effect = [fingers.curses.KEY_RESIZE, "a"]
        with (
            unittest.mock.patch.object(fingers.curses, "curs_set"),
            unittest.mock.patch.object(fingers, "settle_terminal"),
        ):
            self.assertEqual(
                fingers.picker(screen, ["/tmp/a"], {"x": 0, "y": 0, "width": 80}),
                "/tmp/a",
            )

    def test_real_resize_closes_picker(self):
        screen = Mock()
        screen.getmaxyx.side_effect = [(24, 80), (25, 80)]
        screen.get_wch.return_value = fingers.curses.KEY_RESIZE
        with (
            unittest.mock.patch.object(fingers.curses, "curs_set"),
            unittest.mock.patch.object(fingers, "settle_terminal"),
            unittest.mock.patch.object(fingers, "draw_pane"),
            unittest.mock.patch.object(fingers, "draw_text"),
        ):
            self.assertIsNone(
                fingers.picker(screen, ["/tmp/a"], {"x": 0, "y": 0, "width": 80})
            )

    def test_claude_indented_wrapped_path_is_one_target(self):
        path = (
            "../../../../private/tmp/claude-501/-Users-dev-project-example-application/"
            "01234567-89ab-4cde-8012-3456789abcde/scratchpad/example-workbench/"
            "server/prisma/unified/operator/identity-crosswalk-backfill.sql"
        )
        prefix = "  ⎿ \u00a0Read "
        split = 143 - fingers.cell_width(prefix)
        lines = [prefix + path[:split], "     " + path[split:] + " (184 lines)"]
        targets = fingers.extract_targets(lines, wrap_width=146)
        self.assertEqual([target.text for target in targets], [path])
        self.assertEqual(len(targets[0].spans), 2)
        self.assertNotIn("\\n", targets[0].text)
        self.assertEqual(targets[0].spans[1].column, 5)

    def test_path_wraps_across_three_rows(self):
        path = "/tmp/" + "abcdefghij" * 8 + "/file.sql"
        lines = [path[:40], path[40:80], path[80:]]
        targets = fingers.extract_targets(lines, wrap_width=40)
        self.assertEqual([target.text for target in targets], [path])
        self.assertEqual(len(targets[0].spans), 3)

    def test_wrapped_url_trims_only_final_punctuation(self):
        url = "https://example.com/" + "a" * 60 + "/file"
        targets = fingers.extract_targets([url[:40], url[40:] + "),"], wrap_width=40)
        self.assertEqual([target.text for target in targets], [url])
        self.assertFalse(targets[0].spans[-1].text.endswith("),"))

    def test_short_hard_break_is_not_joined(self):
        targets = fingers.extract_targets(
            ["/tmp/one.txt", "src/two.txt"], wrap_width=80
        )
        self.assertEqual(
            [target.text for target in targets], ["/tmp/one.txt", "src/two.txt"]
        )

    def test_new_rooted_path_is_not_a_continuation(self):
        first = "/tmp/" + "a" * 35
        targets = fingers.extract_targets([first, "../separate.txt"], wrap_width=40)
        self.assertEqual(
            [target.text for target in targets], [first, "../separate.txt"]
        )

    def test_cropped_match_can_still_be_selected(self):
        screen = Mock()
        screen.getmaxyx.return_value = (24, 40)
        screen.get_wch.return_value = "a"
        path = "/tmp/" + "a" * 80
        with (
            unittest.mock.patch.object(fingers.curses, "curs_set"),
            unittest.mock.patch.object(fingers, "settle_terminal"),
        ):
            self.assertEqual(
                fingers.picker(screen, [path], {"x": 0, "y": 0, "width": 40}), path
            )

    def test_toggle_closes_only_the_recorded_overlay(self):
        client = Mock(path="/server.sock")
        with (
            tempfile.TemporaryDirectory() as directory,
            unittest.mock.patch.object(
                fingers, "open_picker", return_value="overlay"
            ) as opened,
        ):
            self.assertEqual(
                fingers.toggle_picker(client, "source", directory), "overlay"
            )
            fingers.toggle_picker(client, "overlay", directory)
            opened.assert_called_once_with(client, "source")
            client.call.assert_called_once_with(
                "plugin.pane.close", {"pane_id": "overlay"}
            )
            fingers.toggle_picker(client, "source", directory)
            self.assertEqual(opened.call_count, 2)

    def test_toggle_does_not_close_unrelated_pane(self):
        client = Mock(path="/server.sock")
        with (
            tempfile.TemporaryDirectory() as directory,
            unittest.mock.patch.object(fingers, "open_picker", return_value="overlay"),
        ):
            fingers.toggle_picker(client, "source", directory)
            fingers.toggle_picker(client, "another-pane", directory)
            client.call.assert_not_called()

    def test_toggle_marker_is_private_and_rejects_symlinks(self):
        client = Mock(path="/server.sock")
        with (
            tempfile.TemporaryDirectory() as directory,
            unittest.mock.patch.object(fingers, "open_picker", return_value="overlay"),
        ):
            fingers.toggle_picker(client, "source", directory)
            marker = next(fingers.Path(directory).glob("fingers-overlay-*"))
            self.assertEqual(marker.stat().st_mode & 0o777, 0o600)
            protected = fingers.Path(directory) / "protected"
            protected.write_text("do not touch")
            marker.unlink()
            marker.symlink_to(protected)
            with self.assertRaises(OSError):
                fingers.toggle_picker(client, "source", directory)
            self.assertEqual(protected.read_text(), "do not touch")
            client.call.assert_not_called()

    def test_toggle_is_scoped_to_server(self):
        first = Mock(path="/first.sock")
        second = Mock(path="/second.sock")
        with (
            tempfile.TemporaryDirectory() as directory,
            unittest.mock.patch.object(
                fingers, "open_picker", return_value="overlay"
            ) as opened,
        ):
            fingers.toggle_picker(first, "source", directory)
            fingers.toggle_picker(second, "overlay", directory)
            self.assertEqual(opened.call_count, 2)
            second.call.assert_not_called()

    def test_right_pane_geometry_fits_actual_overlay(self):
        geometry = {
            "x": 146,
            "y": 0,
            "width": 145,
            "height": 75,
            "area_width": 291,
            "area_height": 75,
        }
        fitted = fingers.fit_geometry(geometry, (73, 288))
        self.assertEqual(fitted["x"], 144)
        self.assertEqual(fitted["x"] + fitted["width"], 288)
        self.assertEqual(fitted["height"], 73)

    def test_background_is_drawn_without_hints(self):
        screen = Mock()
        screen.getmaxyx.return_value = (24, 80)
        screen.get_wch.return_value = "a"
        left = {"x": 0, "y": 0, "width": 40, "height": 24}
        right = {"x": 40, "y": 0, "width": 40, "height": 24}
        with (
            unittest.mock.patch.object(fingers.curses, "curs_set"),
            unittest.mock.patch.object(fingers, "settle_terminal"),
            unittest.mock.patch.object(fingers, "draw_pane") as draw,
        ):
            result = fingers.picker(
                screen,
                ["/tmp/focused"],
                right,
                backdrop=[(left, ["/tmp/neighbor"], None)],
            )
        self.assertEqual(result, "/tmp/focused")
        self.assertEqual(draw.call_count, 2)
        self.assertEqual(draw.call_args_list[0].args[1], ["/tmp/neighbor"])

    def test_startup_resize_is_drained(self):
        screen = Mock()
        screen.get_wch.side_effect = [fingers.curses.KEY_RESIZE, fingers.curses.error()]
        fingers.settle_terminal(screen)
        self.assertEqual(screen.get_wch.call_count, 2)
        self.assertEqual(screen.timeout.call_args.args, (-1,))

    def test_startup_preserves_early_keypress(self):
        screen = Mock()
        screen.get_wch.side_effect = [fingers.curses.KEY_RESIZE, "a"]
        with unittest.mock.patch.object(fingers.curses, "unget_wch") as unget:
            fingers.settle_terminal(screen)
        unget.assert_called_once_with("a")


if __name__ == "__main__":
    unittest.main()
