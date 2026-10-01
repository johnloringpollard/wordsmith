"""Private persistence for instruction drafts and saved instructions."""

import json
import os
from pathlib import Path
import tempfile


DEFAULT_INSTRUCTION = "Reword for clarity and keep it concise. No em dashes."
MAX_INSTRUCTION_LENGTH = 8000
MAX_SAVED_INSTRUCTIONS = 100
MAX_FILE_BYTES = 4 * 1024 * 1024


class InstructionError(Exception):
    pass


class InstructionStore:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else (
            Path.home() / ".config/rewerd/instructions.json"
        )

    @staticmethod
    def _validate_text(text, *, allow_blank):
        if not isinstance(text, str):
            raise InstructionError("Instructions must be text.")
        if len(text) > MAX_INSTRUCTION_LENGTH:
            raise InstructionError("Instructions must be at most 8000 characters.")
        if not allow_blank and not text.strip():
            raise InstructionError("Saved instructions cannot be blank.")
        try:
            text.encode("utf-8")
        except UnicodeError as error:
            raise InstructionError("Instructions must contain valid Unicode text.") from error

    @classmethod
    def _validate_state(cls, state):
        if not isinstance(state, dict) or set(state) != {"last", "saved"}:
            raise InstructionError("Invalid instruction file format.")
        cls._validate_text(state["last"], allow_blank=True)
        saved = state["saved"]
        if not isinstance(saved, list) or len(saved) > MAX_SAVED_INSTRUCTIONS:
            raise InstructionError("Invalid saved instruction list.")
        for text in saved:
            cls._validate_text(text, allow_blank=False)
        if len(set(saved)) != len(saved):
            raise InstructionError("Saved instructions contain duplicates.")

    def read(self):
        try:
            with self.path.open("rb") as source:
                data = source.read(MAX_FILE_BYTES + 1)
        except FileNotFoundError:
            return {"last": DEFAULT_INSTRUCTION, "saved": []}
        except OSError as error:
            raise InstructionError("Cannot read the instruction file.") from error
        if len(data) > MAX_FILE_BYTES:
            raise InstructionError("The instruction file is too large.")
        try:
            state = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeError, RecursionError) as error:
            raise InstructionError("The instruction file is corrupt.") from error
        self._validate_state(state)
        return state

    def _write(self, state):
        self._validate_state(state)
        data = (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if len(data) > MAX_FILE_BYTES:
            raise InstructionError("The instruction file would be too large.")
        temporary = None
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.path.parent.chmod(0o700)
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=".instructions-", dir=self.path.parent, delete=False
            ) as target:
                temporary = Path(target.name)
                os.fchmod(target.fileno(), 0o600)
                target.write(data)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.path)
            temporary = None
        except OSError as error:
            raise InstructionError("Cannot save the instruction file.") from error
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
        return state

    def remember(self, text):
        self._validate_text(text, allow_blank=True)
        state = self.read()
        state["last"] = text
        return self._write(state)

    def save(self, text):
        self._validate_text(text, allow_blank=False)
        state = self.read()
        if text not in state["saved"]:
            if len(state["saved"]) >= MAX_SAVED_INSTRUCTIONS:
                raise InstructionError("You can save at most 100 instructions.")
            state["saved"].append(text)
        state["last"] = text
        return self._write(state)

    def remove(self, text):
        self._validate_text(text, allow_blank=True)
        state = self.read()
        if text in state["saved"]:
            state["saved"].remove(text)
            return self._write(state)
        return state
