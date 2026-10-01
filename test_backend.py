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


class RetentionTests(unittest.TestCase):
    def setUp(self):
        from backend import Backend
        with patch('backend.ConfigStore'), patch('backend.InstructionStore'):
            self.backend = Backend()
        self.backend.emit = Mock()
        self.original = Selection('original', '0x123', 5, 'id', 'editor', True)
        self.backend.selection = self.original
        self.backend.result = 'rewrite'
        self.backend.clipboard_baseline = 'original'

    def capture(self, selected=None, clipboard='original', error=None):
        snapshot = ClipboardSnapshot('text/plain', clipboard.encode())
        with patch('backend.ClipboardSnapshot.capture', return_value=snapshot), \
                patch('backend.Selection.capture', return_value=selected, side_effect=error):
            self.backend.handle({'type': 'capture', 'id': 2})
        return self.backend.emit.call_args

    def fallback(self, text):
        return Selection(text, '', 0, '', 'Clipboard', False)

    def test_same_selection_preserves_result_and_original_target(self):
        event = self.capture(self.original)
        self.assertTrue(event.args[2]['retained'])
        self.assertEqual(event.args[2]['result'], 'rewrite')
        self.assertIs(self.backend.selection, self.original)

    def test_unchanged_clipboard_preserves_selection_target_and_result(self):
        event = self.capture(self.fallback('original'))
        self.assertTrue(event.args[2]['retained'])
        self.assertIs(self.backend.selection, self.original)
        self.assertEqual(self.backend.result, 'rewrite')

    def test_new_selection_resets_even_with_unchanged_clipboard(self):
        from dataclasses import replace
        event = self.capture(replace(self.original, text='new selection'))
        self.assertFalse(event.args[2]['retained'])
        self.assertEqual(self.backend.result, '')
        self.assertEqual(self.backend.selection.text, 'new selection')

    def test_same_text_in_another_window_starts_new_session(self):
        from dataclasses import replace
        event = self.capture(replace(self.original, address='0x456'))
        self.assertFalse(event.args[2]['retained'])
        self.assertEqual(self.backend.result, '')
        self.assertEqual(self.backend.selection.address, '0x456')

    def test_new_clipboard_starts_copy_only_session(self):
        event = self.capture(self.fallback('new clipboard'), 'new clipboard')
        self.assertFalse(event.args[2]['retained'])
        self.assertFalse(event.args[2]['canReplace'])
        self.assertEqual(self.backend.result, '')

    def test_own_copy_and_replace_are_not_new_clipboard_input(self):
        for operation in ('copy', 'replace'):
            with self.subTest(operation=operation), patch('backend.copy') as write, \
                    patch.object(Selection, 'replace') as paste:
                self.backend.handle({'type': operation})
                (write if operation == 'copy' else paste).assert_called_once_with('rewrite')
                event = self.capture(self.fallback('rewrite'), 'rewrite')
                self.assertTrue(event.args[2]['retained'])
                self.assertEqual(event.args[2]['text'], 'original')
                self.assertEqual(event.args[2]['result'], 'rewrite')
                self.assertIs(self.backend.selection, self.original)

    def test_explicitly_selecting_copied_output_is_new_input(self):
        from dataclasses import replace
        with patch('backend.copy'):
            self.backend.handle({'type': 'copy'})
        event = self.capture(replace(self.original, text='rewrite'), 'rewrite')
        self.assertFalse(event.args[2]['retained'])
        self.assertEqual(self.backend.result, '')

    def test_no_input_retains_session_but_first_open_reports_error(self):
        from backend import NoSelectedText
        event = self.capture(clipboard='', error=NoSelectedText('Select text'))
        self.assertTrue(event.args[2]['retained'])
        self.assertEqual(self.backend.result, 'rewrite')
        self.backend.selection = None
        event = self.capture(clipboard='', error=NoSelectedText('Select text'))
        self.assertEqual(event.kwargs['error'], 'Select text')

    def test_capture_failure_preserves_work_and_blocks_replace_until_recapture(self):
        event = self.capture(error=DesktopError('Focus changed'))
        self.assertEqual(event.kwargs['error'], 'Focus changed')
        self.assertIs(self.backend.selection, self.original)
        self.assertEqual(self.backend.result, 'rewrite')
        with patch.object(Selection, 'replace') as paste, patch('backend.copy') as write:
            self.backend.handle({'type': 'replace'})
            paste.assert_not_called()
            self.backend.handle({'type': 'copy'})
            write.assert_called_once_with('rewrite')
            self.capture(self.original)
            self.backend.handle({'type': 'replace'})
            paste.assert_called_once_with('rewrite')

    def test_reopen_while_generation_is_pending(self):
        import threading
        from backend import Backend, NoSelectedText, ProviderError
        from dataclasses import replace

        for scenario in ('same', 'clipboard', 'empty', 'new', 'capture_error',
                         'provider_error', 'unexpected_error', 'cancel'):
            with self.subTest(scenario=scenario):
                started = threading.Event()
                finish = threading.Event()
                workers = []
                real_thread = threading.Thread

                def track_thread(*args, **kwargs):
                    worker = real_thread(*args, **kwargs)
                    workers.append(worker)
                    return worker

                def slow_generate(*_):
                    started.set()
                    if not finish.wait(2):
                        raise RuntimeError('Timed out waiting for capture')
                    if scenario == 'provider_error':
                        raise ProviderError('Provider unavailable')
                    if scenario == 'unexpected_error':
                        raise RuntimeError('Unexpected failure')
                    return 'late rewrite'

                with patch('backend.ConfigStore'), patch('backend.InstructionStore'):
                    self.backend = Backend()
                self.backend.selection = self.original
                self.backend.clipboard_baseline = 'original'
                self.backend.emit = Mock()
                with patch('backend.generate', side_effect=slow_generate), \
                        patch('backend.threading.Thread', side_effect=track_thread):
                    self.backend.handle({'type': 'generate', 'id': 10, 'prompt': 'rewrite'})
                    try:
                        self.assertTrue(started.wait(2))
                        self.assertEqual(self.backend.active_request_id, 10)
                        selected = self.original
                        error = None
                        if scenario == 'clipboard':
                            selected = self.fallback('original')
                        elif scenario == 'empty':
                            error = NoSelectedText('Select text')
                        elif scenario == 'new':
                            selected = replace(self.original, text='new selection')
                        elif scenario == 'capture_error':
                            error = DesktopError('Focus changed')
                        event = self.capture(selected, error=error)
                        if scenario == 'capture_error':
                            self.assertEqual(event.kwargs['error'], 'Focus changed')
                        else:
                            self.assertEqual(event.args[2]['generationId'], 0 if scenario == 'new' else 10)
                        if scenario == 'cancel':
                            self.backend.handle({'type': 'cancel', 'id': 11})
                        self.backend.emit.reset_mock()
                    finally:
                        finish.set()
                        for worker in workers:
                            worker.join(2)
                            self.assertFalse(worker.is_alive())

                self.assertEqual(self.backend.active_request_id, 0)
                if scenario in ('new', 'cancel'):
                    self.backend.emit.assert_not_called()
                    self.assertEqual(self.backend.result, '')
                elif scenario in ('provider_error', 'unexpected_error'):
                    self.assertEqual(self.backend.emit.call_args.args, ('generate', 10))
                    self.assertTrue(self.backend.emit.call_args.kwargs['error'])
                    self.assertEqual(self.backend.result, '')
                else:
                    self.backend.emit.assert_called_once_with('generate', 10, {'text': 'late rewrite'})
                    self.assertEqual(self.backend.result, 'late rewrite')
                    if scenario == 'capture_error':
                        with patch.object(Selection, 'replace') as paste, patch('backend.copy') as write:
                            self.backend.handle({'type': 'replace'})
                            paste.assert_not_called()
                            self.backend.handle({'type': 'copy'})
                            write.assert_called_once_with('late rewrite')
                    event = self.capture(self.original)
                    self.assertEqual(event.args[2]['generationId'], 0)
                    self.assertEqual(event.args[2]['result'], 'late rewrite')


class WritingDefaultsTests(unittest.TestCase):
    def test_save_defaults_dispatch_and_error(self):
        import backend
        import tempfile
        from pathlib import Path
        from providers import ConfigStore
        with tempfile.TemporaryDirectory() as directory:
            worker = backend.Backend()
            worker.config = ConfigStore(Path(directory) / "settings.json")
            worker.emit = Mock()
            worker.handle({"type": "save_defaults", "id": 12, "defaultInstructions": "Prefer short sentences."})
            worker.emit.assert_called_once_with("save_defaults", 12, worker.config.public())
            self.assertEqual(worker.config.credentials()["defaultInstructions"], "Prefer short sentences.")
            worker.emit.reset_mock()
            worker.handle({"type": "save_defaults", "id": 13, "defaultInstructions": None})
            self.assertTrue(worker.emit.call_args.kwargs["error"])
            self.assertEqual(worker.config.public()["defaultInstructions"], "Prefer short sentences.")


if __name__ == "__main__":
    unittest.main()
