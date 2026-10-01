import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from instructions import (
    DEFAULT_INSTRUCTION,
    MAX_FILE_BYTES,
    InstructionError,
    InstructionStore,
)


class InstructionStoreTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "private" / "instructions.json"
        self.store = InstructionStore(self.path)

    def test_default_is_not_written_until_edit(self):
        self.assertEqual(
            DEFAULT_INSTRUCTION,
            "Reword for clarity and keep it concise.",
        )
        self.assertEqual(self.store.read(), {"last": DEFAULT_INSTRUCTION, "saved": []})
        self.assertFalse(self.path.exists())
        with patch("instructions.Path.home", return_value=Path(self.directory.name)):
            self.assertEqual(
                InstructionStore().path,
                Path(self.directory.name) / ".config/rewerd/instructions.json",
            )

    def test_old_stock_draft_migrates_without_changing_saved_prompts(self):
        previous_default = "Reword for clarity and keep it concise. No em dashes."
        custom = "Use em dashes and an emoji in every sentence."
        state = {"last": previous_default, "saved": [previous_default, custom]}
        self.path.parent.mkdir()
        self.path.write_text(json.dumps(state))
        before = self.path.read_bytes()
        self.assertEqual(self.store.read(), {**state, "last": DEFAULT_INSTRUCTION})
        self.assertEqual(self.path.read_bytes(), before)

    def test_crud_reopen_and_last_independent_of_saved(self):
        self.store.save("First")
        self.store.save("Second")
        self.store.remember("Unsaved draft")
        reopened = InstructionStore(self.path)
        self.assertEqual(reopened.read(), {"last": "Unsaved draft", "saved": ["First", "Second"]})
        reopened.remove("First")
        self.assertEqual(reopened.remove("First"), {"last": "Unsaved draft", "saved": ["Second"]})
        reopened.remember("Second")
        self.assertEqual(reopened.remove("Second"), {"last": "Second", "saved": []})
        self.assertEqual(self.store.read(), {"last": "Second", "saved": []})

    def test_exact_text_dedup_and_order(self):
        text = "  Rewrite\nwith café 🐈\t "
        self.store.save(text)
        self.store.save(text.strip())
        self.store.save(text)
        self.assertEqual(self.store.read(), {"last": text, "saved": [text, text.strip()]})
        self.store.remove(text.strip())
        self.assertEqual(self.store.read()["saved"], [text])

    def test_blank_drafts_allowed_but_blank_favorites_rejected(self):
        for text in ("", " \n\t"):
            self.assertEqual(self.store.remember(text)["last"], text)
            with self.assertRaises(InstructionError):
                self.store.save(text)
            self.assertEqual(InstructionStore(self.path).read()["last"], text)

    def test_character_limit_and_invalid_inputs(self):
        self.store.save("🐈" * 8000)
        for method in (self.store.save, self.store.remember, self.store.remove):
            for text in ("a" * 8001, None, 42, "\ud800"):
                with self.assertRaises(InstructionError):
                    method(text)
        self.assertEqual(self.store.read()["last"], "🐈" * 8000)

    def test_list_limit_allows_existing_favorite_and_large_unicode(self):
        values = [str(i) + "🐈" * 7998 for i in range(100)]
        for text in values:
            self.store.save(text)
        self.assertEqual(self.store.save(values[0])["saved"], values)
        with self.assertRaises(InstructionError):
            self.store.save("One too many")
        self.assertEqual(self.store.read()["last"], values[0])

    def test_private_permissions(self):
        self.path.parent.mkdir(mode=0o755)
        self.store.save("Private")
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.path.chmod(0o644)
        self.store.remember("Another")
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_atomic_failure_keeps_previous_data_and_cleans_temporary(self):
        self.store.save("Keep me")
        before = self.path.read_bytes()
        for operation in ("instructions.os.replace", "instructions.os.fsync"):
            with patch(operation, side_effect=OSError("disk failure")):
                with self.assertRaises(InstructionError):
                    self.store.save("Do not commit")
            self.assertEqual(self.path.read_bytes(), before)
            self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_corrupt_files_are_never_overwritten(self):
        self.path.parent.mkdir()
        invalid = [
            b"not json", b"\xff", b"[", b"[]", b"{}",
            json.dumps({"last": None, "saved": []}).encode(),
            json.dumps({"last": "", "saved": "bad"}).encode(),
            json.dumps({"last": "", "saved": [" "]}).encode(),
            json.dumps({"last": "", "saved": ["same", "same"]}).encode(),
            json.dumps({"last": "", "saved": list(map(str, range(101)))}).encode(),
            json.dumps({"last": "x" * 8001, "saved": []}).encode(),
            b" " * (MAX_FILE_BYTES + 1),
        ]
        for data in invalid:
            with self.subTest(data=data[:50]):
                self.path.write_bytes(data)
                for operation in (self.store.read, lambda: self.store.remember("New"),
                                  lambda: self.store.save("New"), lambda: self.store.remove("New")):
                    with self.assertRaises(InstructionError):
                        operation()
                    self.assertEqual(self.path.read_bytes(), data)


class StockPromptMigrationTests(unittest.TestCase):
    def test_only_exact_legacy_last_prompt_is_migrated(self):
        from instructions import LEGACY_DEFAULT_INSTRUCTIONS, DEFAULT_INSTRUCTION, InstructionStore
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instructions.json"
            for last in (*LEGACY_DEFAULT_INSTRUCTIONS, *(text + "\n" for text in LEGACY_DEFAULT_INSTRUCTIONS), DEFAULT_INSTRUCTION + " Keep links.", "  Custom\n", ""):
                saved = [*sorted(LEGACY_DEFAULT_INSTRUCTIONS), "Custom"]
                path.write_text(json.dumps({"last": last, "saved": saved}))
                state = InstructionStore(path).read()
                self.assertEqual(state["last"], DEFAULT_INSTRUCTION if last.strip() in LEGACY_DEFAULT_INSTRUCTIONS else last)
                self.assertEqual(state["saved"], saved)


if __name__ == "__main__":
    unittest.main()
