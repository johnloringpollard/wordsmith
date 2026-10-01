import subprocess
import unittest
from unittest.mock import Mock, patch
from backend import ClipboardSnapshot, DesktopError, Selection, copy, clipboard as read_clipboard


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.selection = Selection("original", "0x123", 5, "id", "editor", True)
        self.window = {"address": "0x123", "pid": 5, "stableId": "id", "class": "editor"}
        self.active = self.mock_tool("backend.active_window", return_value=self.window)
        self.copy = self.mock_tool("backend.copy")
        self.clipboard = self.mock_tool("backend.clipboard", return_value="selected text")
        self.snapshot = self.mock_tool("backend.ClipboardSnapshot.capture").return_value
        self.snapshot.plain_text.return_value = "Previously copied text"
        self.dispatch = self.mock_tool("backend.dispatch")
        self.mock_tool("backend.time.sleep")
        self.mock_tool("backend.uuid.uuid4", return_value=Mock(hex="test"))

    def mock_tool(self, name, **kwargs):
        patcher = patch(name, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_actual_selection_wins_over_existing_clipboard(self):
        selected = Selection.capture()
        self.assertEqual(selected.text, "selected text")
        self.assertTrue(selected.can_replace)
        self.assertEqual(self.copy.call_args.args, ("edit-ai-selection-check-test",))
        self.assertIn('key = "C"', self.dispatch.call_args_list[0].args[0])
        self.assertIn('address:0x123', self.dispatch.call_args_list[0].args[0])
        self.snapshot.restore.assert_not_called()

    def test_no_selection_uses_preserved_clipboard_without_replacement(self):
        self.clipboard.return_value = "edit-ai-selection-check-test"
        selected = Selection.capture()
        self.assertEqual(selected.text, "Previously copied text")
        self.assertEqual(selected.app, "Clipboard")
        self.assertFalse(selected.can_replace)
        with self.assertRaisesRegex(DesktopError, "Copy the result"):
            selected.replace("rewrite")
        self.assertEqual(self.clipboard.call_count, 20)
        self.snapshot.restore.assert_called_once_with()

    def test_transient_empty_clipboard_waits_for_selected_text(self):
        self.clipboard.side_effect = ["", "edit-ai-selection-check-test", "fresh"]
        self.assertEqual(Selection.capture().text, "fresh")

    @patch("backend.subprocess.run", return_value=Mock(returncode=1, stderr="Wayland connection failed"))
    def test_clipboard_command_failure_does_not_fall_back(self, command):
        self.clipboard.side_effect = read_clipboard
        with self.assertRaisesRegex(DesktopError, "Could not read the clipboard"):
            Selection.capture()
        self.snapshot.restore.assert_called_once_with()
        self.snapshot.plain_text.assert_not_called()
        command.assert_called_once()

    def test_empty_selection_times_out_and_restores_clipboard(self):
        self.clipboard.return_value = ""
        self.snapshot.plain_text.return_value = ""
        with self.assertRaisesRegex(DesktopError, "Select text or copy some text"):
            Selection.capture()
        self.snapshot.restore.assert_called_once_with()

    def test_whitespace_selection_restores_clipboard(self):
        self.clipboard.return_value = "  "
        self.assertEqual(Selection.capture().text, "Previously copied text")
        self.snapshot.restore.assert_called_once_with()

    def test_oversized_clipboard_is_rejected_when_no_selection(self):
        self.clipboard.return_value = "edit-ai-selection-check-test"
        self.snapshot.plain_text.return_value = "a" * 100001
        with self.assertRaisesRegex(DesktopError, "Copy a shorter passage"):
            Selection.capture()
        self.snapshot.restore.assert_called_once_with()

    def test_oversized_selection_restores_clipboard(self):
        self.clipboard.return_value = "a" * 100001
        with self.assertRaisesRegex(DesktopError, "shorter passage"):
            Selection.capture()
        self.snapshot.restore.assert_called_once_with()

    def test_terminal_uses_insert_and_never_accepts_replacement(self):
        self.window["tags"] = ["terminal*"]
        selected = Selection.capture()
        self.assertFalse(selected.can_replace)
        self.assertIn('key = "Insert"', self.dispatch.call_args_list[0].args[0])
        with self.assertRaisesRegex(DesktopError, "unavailable"):
            selected.replace("rewrite")

    def test_no_active_window_uses_clipboard_without_sending_keys(self):
        self.active.return_value = {}
        selected = Selection.capture()
        self.assertEqual(selected.text, "Previously copied text")
        self.assertFalse(selected.can_replace)
        self.snapshot.restore.assert_not_called()
        self.copy.assert_not_called()
        self.dispatch.assert_not_called()

    def test_copy_dispatch_error_restores_clipboard_and_releases_key(self):
        self.dispatch.side_effect = [DesktopError("copy failed"), None]
        with self.assertRaisesRegex(DesktopError, "copy failed"):
            Selection.capture()
        self.assertIn('state = "up"', self.dispatch.call_args.args[0])
        self.snapshot.restore.assert_called_once_with()

    def test_copy_write_failure_restores_clipboard(self):
        self.copy.side_effect = DesktopError("write failed")
        with self.assertRaisesRegex(DesktopError, "write failed"):
            Selection.capture()
        self.snapshot.restore.assert_called_once_with()
        self.dispatch.assert_not_called()

    def test_focus_change_during_copy_rejects_text(self):
        self.active.side_effect = [self.window, self.window, self.window,
                                   dict(self.window, address="0x456")]
        with self.assertRaisesRegex(DesktopError, "Focus changed"):
            Selection.capture()
        self.snapshot.restore.assert_called_once_with()

    def test_wrong_focus_or_reused_identity(self):
        for change in ({"address": "0x456"}, {"pid": 6}, {"stableId": "new"}):
            with self.subTest(change=change):
                self.active.return_value = dict(self.window, **change)
                with self.assertRaisesRegex(DesktopError, "Focus changed"):
                    self.selection.ensure_focus()

    @patch("backend.run", return_value='[{"address":"0x123","pid":5,"stableId":"new"}]')
    def test_reused_window_address_is_rejected(self, _):
        self.assertIsNone(self.selection.target())

    @patch.object(Selection, "target", return_value=None)
    def test_closed_window_never_touches_clipboard(self, _):
        with self.assertRaises(DesktopError):
            self.selection.replace("rewrite")
        self.copy.assert_not_called()
        ClipboardSnapshot.capture.assert_not_called()

    @patch.object(Selection, "target", return_value={"pid": 5})
    def test_changed_selection_does_not_paste_and_restores_clipboard(self, _):
        with self.assertRaisesRegex(DesktopError, "no longer selected"):
            self.selection.replace("rewrite")
        self.snapshot.restore.assert_called_once_with()
        self.assertFalse(any('key = "V"' in c.args[0] for c in self.dispatch.call_args_list))

    @patch.object(Selection, "target", return_value={"pid": 5})
    def test_matching_selection_pastes_result(self, _):
        self.clipboard.return_value = "original"
        self.selection.replace("rewrite")
        self.assertEqual(self.copy.call_args.args, ("rewrite",))
        self.assertIn('key = "V"', self.dispatch.call_args.args[0])
        self.snapshot.restore.assert_not_called()

    @patch.object(Selection, "target", return_value={"pid": 5})
    def test_replacement_also_requires_fresh_copy(self, _):
        self.clipboard.return_value = "edit-ai-selection-check-test"
        with self.assertRaisesRegex(DesktopError, "Could not read selected text"):
            self.selection.replace("rewrite")
        self.snapshot.restore.assert_called_once_with()
        self.assertFalse(any('key = "V"' in c.args[0] for c in self.dispatch.call_args_list))


class ClipboardTests(unittest.TestCase):
    def test_only_plain_text_is_usable_as_rewrite_input(self):
        text = "Hello café\nSecond line"
        self.assertEqual(ClipboardSnapshot("text/plain;charset=utf-8", text.encode()).plain_text(), text)
        for mime, data in [(None, b""), ("image/png", b"PNG"),
                           ("text/html", b"<b>Hello</b>"), ("text/plain", b"\xff")]:
            with self.subTest(mime=mime, data=data):
                self.assertEqual(ClipboardSnapshot(mime, data).plain_text(), "")

    @patch("backend.subprocess.run")
    def test_binary_image_snapshot_restores_original_mime_and_bytes(self, run):
        run.side_effect = [Mock(returncode=0, stdout=b"image/png\nimage/jpeg\n"),
                           Mock(returncode=0, stdout=b"\x89PNG\x00\xff")]
        snapshot = ClipboardSnapshot.capture()
        with patch("backend.copy") as write:
            snapshot.restore()
        write.assert_called_once_with(b"\x89PNG\x00\xff", "image/png")

    @patch("backend.subprocess.run")
    def test_empty_clipboard_snapshot_restores_no_selection(self, run):
        run.return_value = Mock(returncode=1, stderr=b"Nothing is copied")
        snapshot = ClipboardSnapshot.capture()
        with patch("backend.run") as command:
            snapshot.restore()
        command.assert_called_once_with(["wl-copy", "--clear"])

    @patch("backend.subprocess.run")
    def test_snapshot_error_does_not_touch_clipboard(self, run):
        run.return_value = Mock(returncode=1, stderr=b"Wayland connection failed")
        with patch("backend.copy") as write, self.assertRaises(DesktopError):
            ClipboardSnapshot.capture()
        write.assert_not_called()

    @patch("backend.subprocess.run")
    def test_binary_copy_does_not_hold_daemon_output_pipe(self, run):
        copy(b"\xff", "image/png")
        self.assertFalse(run.call_args.kwargs["text"])
        self.assertEqual(run.call_args.kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs["stderr"], subprocess.DEVNULL)

    @patch("backend.subprocess.run", side_effect=subprocess.TimeoutExpired("wl-paste", 0.2))
    def test_clipboard_read_timeout_is_bounded_and_treated_as_no_text(self, run):
        from backend import clipboard
        self.assertEqual(clipboard(), "")
        self.assertEqual(run.call_args.kwargs["timeout"], 0.2)


class GenerationTests(unittest.TestCase):
    def test_cancel_discards_completed_inflight_response(self):
        import threading
        from backend import Backend
        started = threading.Event()
        finish = threading.Event()
        def slow_generate(*_):
            started.set()
            self.assertTrue(finish.wait(2))
            return 'stale rewrite'
        with patch('backend.ConfigStore'), patch('backend.generate', side_effect=slow_generate):
            backend = Backend()
            backend.generation = 1
            backend.emit = unittest.mock.Mock()
            thread = threading.Thread(target=backend.rewrite, args=(10, 1, {}, 'reword this', 'source'))
            thread.start()
            self.assertTrue(started.wait(2))
            backend.handle({'type': 'cancel', 'id': 11})
            finish.set()
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(backend.result, '')
            self.assertFalse(any(call.args[0] == 'generate' for call in backend.emit.call_args_list))

    def test_successful_result_is_available_for_copy(self):
        from backend import Backend
        with patch('backend.ConfigStore'), patch('backend.generate', return_value='rewrite'), patch('backend.copy') as copy:
            backend = Backend()
            backend.emit = unittest.mock.Mock()
            backend.rewrite(1, 0, {}, 'reword this', 'source')
            backend.handle({'type': 'copy', 'id': 2})
            copy.assert_called_once_with('rewrite')


if __name__ == "__main__":
    unittest.main()
