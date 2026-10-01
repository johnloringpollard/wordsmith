#!/usr/bin/env python3
import json
import re
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, replace

from providers import ConfigStore, ProviderError, generate
from instructions import InstructionError, InstructionStore

MAX_TEXT = 100_000


class DesktopError(Exception):
    pass


class NoSelectedText(DesktopError):
    pass


def run(args, text=None, timeout=4):
    try:
        result = subprocess.run(args, input=text, text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DesktopError(f"Desktop command unavailable: {args[0]}") from exc
    if result.returncode:
        raise DesktopError(f"Desktop command failed: {args[0]}")
    return result.stdout


def clipboard():
    try:
        result = subprocess.run(["wl-paste", "--no-newline", "--type", "text"],
                                text=True, capture_output=True, timeout=0.2)
    except subprocess.TimeoutExpired:
        return ""
    except (OSError, UnicodeError) as exc:
        raise DesktopError("Could not read the clipboard. Try again.") from exc
    if result.returncode:
        if "Nothing is copied" in result.stderr or "No selection" in result.stderr:
            return ""
        raise DesktopError("Could not read the clipboard. Try again.")
    return result.stdout


def copy(text, mime="text/plain;charset=utf-8"):
    try:
        subprocess.run(["wl-copy", "--type", mime], input=text,
                       text=isinstance(text, str), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=4, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise DesktopError("Could not write to the clipboard.") from exc


def active_window():
    return json.loads(run(["hyprctl", "-j", "activewindow"]))


def dispatch(expression):
    result = run(["hyprctl", "dispatch", expression])
    if result.strip() != "ok":
        raise DesktopError("The desktop could not focus the original app.")


@dataclass(frozen=True)
class ClipboardSnapshot:
    mime: str | None
    data: bytes = b""

    @classmethod
    def capture(cls):
        try:
            result = subprocess.run(["wl-paste", "--list-types"], capture_output=True, timeout=4)
            if result.returncode:
                if b"Nothing is copied" in result.stderr or b"No selection" in result.stderr:
                    return cls(None)
                raise DesktopError("Could not preserve the clipboard. Try again.")
            types = result.stdout.decode().splitlines()
            mime = next((t for t in ("text/plain;charset=utf-8", "text/plain", "image/png")
                         if t in types), next((t for t in types if "/" in t), None))
            if mime is None:
                raise DesktopError("Could not preserve this clipboard format.")
            result = subprocess.run(["wl-paste", "--no-newline", "--type", mime],
                                    capture_output=True, timeout=4)
            if result.returncode:
                raise DesktopError("Could not preserve the clipboard. Try again.")
            return cls(mime, result.stdout)
        except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
            raise DesktopError("Could not preserve the clipboard. Try again.") from exc

    def restore(self):
        if self.mime is None:
            run(["wl-copy", "--clear"])
        else:
            copy(self.data, self.mime)

    def plain_text(self):
        if not self.mime or self.mime.split(";", 1)[0] != "text/plain":
            return ""
        try:
            return self.data.decode("utf-8")
        except UnicodeError:
            return ""


@dataclass(frozen=True)
class Selection:
    text: str
    address: str
    pid: int
    stable_id: str
    app: str
    can_replace: bool

    @classmethod
    def from_clipboard(cls, snapshot):
        text = snapshot.plain_text()
        if not text.strip():
            raise DesktopError("Select text or copy some text, then open Rewerd.")
        if len(text) > MAX_TEXT:
            raise DesktopError("Copy a shorter passage, up to 100,000 characters.")
        return cls(text, "", 0, "", "Clipboard", False)

    @classmethod
    def capture(cls):
        window = active_window()
        previous = ClipboardSnapshot.capture()
        address = window.get("address", "")
        if not isinstance(address, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", address):
            return cls.from_clipboard(previous)
        terminal = any(tag.rstrip("*") == "terminal" for tag in window.get("tags", []))
        selection = cls("", address, window.get("pid", 0), window.get("stableId", ""),
                        window.get("class", "your app"), not terminal)
        try:
            text = selection.read_selected_text("Insert" if terminal else "C")
            if not text.strip():
                raise NoSelectedText("No text selected.")
            if len(text) > MAX_TEXT:
                raise DesktopError("Select a shorter passage, up to 100,000 characters.")
            return replace(selection, text=text)
        except NoSelectedText:
            previous.restore()
            return cls.from_clipboard(previous)
        except Exception:
            previous.restore()
            raise

    def read_selected_text(self, key="C"):
        self.ensure_focus()
        sentinel = "edit-ai-selection-check-" + uuid.uuid4().hex
        copy(sentinel)
        self.chord(key)
        for _ in range(20):
            selected = clipboard()
            self.ensure_focus()
            if selected and selected != sentinel:
                return selected
            time.sleep(0.05)
        raise NoSelectedText("Could not read selected text. Select text in your app and try again.")

    def target(self):
        clients = json.loads(run(["hyprctl", "-j", "clients"]))
        return next((w for w in clients if w.get("address") == self.address
                     and w.get("pid") == self.pid and w.get("stableId", "") == self.stable_id), None)

    def ensure_focus(self):
        window = active_window()
        if (window.get("address") != self.address or window.get("pid") != self.pid
                or window.get("stableId", "") != self.stable_id):
            raise DesktopError("Focus changed. Select the text again and reopen Rewerd.")

    def chord(self, key):
        self.ensure_focus()
        target = f'window = "address:{self.address}"'
        down = f'hl.dsp.send_key_state({{ mods = "CTRL", key = "{key}", state = "down", {target} }})'
        up = f'hl.dsp.send_key_state({{ mods = "CTRL", key = "{key}", state = "up", {target} }})'
        try:
            dispatch(down)
            time.sleep(0.05)
        finally:
            dispatch(up)

    def replace(self, result):
        if not self.can_replace or not self.target():
            raise DesktopError("The original app is unavailable. Copy the result instead.")
        previous = ClipboardSnapshot.capture()
        pasted = False
        try:
            dispatch(f'hl.dsp.focus({{ window = "address:{self.address}" }})')
            time.sleep(0.15)
            self.ensure_focus()
            selected = self.read_selected_text()
            if selected != self.text:
                raise DesktopError("The original text is no longer selected. Select it again in the original app, then reopen this panel and retry, or copy the result.")
            self.ensure_focus()
            copy(result)
            self.chord("V")
            pasted = True
        finally:
            if not pasted:
                previous.restore()


class Backend:
    def __init__(self):
        self.config = ConfigStore()
        self.instructions = InstructionStore()
        self.selection = None
        self.result = ""
        self.generation = 0
        self.lock = threading.RLock()

    def emit(self, kind, request_id=0, data=None, error=""):
        with self.lock:
            print(json.dumps({"type": kind, "id": request_id, "data": data, "error": error}), flush=True)

    def rewrite(self, request_id, generation, credentials, prompt, source):
        try:
            result = generate(credentials, prompt, source)
            with self.lock:
                if generation == self.generation:
                    self.result = result
                    self.emit("generate", request_id, {"text": result})
        except ProviderError as exc:
            with self.lock:
                if generation == self.generation:
                    self.emit("generate", request_id, error=str(exc))
        except Exception:
            with self.lock:
                if generation == self.generation:
                    self.emit("generate", request_id, error="The provider returned an unexpected response. Try again.")

    def handle(self, message):
        with self.lock:
            kind = message.get("type")
            request_id = message.get("id", 0)
            try:
                if kind == "capture":
                    self.generation += 1
                    self.result = ""
                    self.selection = None
                    self.selection = Selection.capture()
                    self.emit(kind, request_id, {"text": self.selection.text, "app": self.selection.app,
                                                 "canReplace": self.selection.can_replace})
                elif kind == "instructions":
                    self.emit(kind, request_id, self.instructions.read())
                elif kind == "instruction_remember":
                    self.emit(kind, request_id, self.instructions.remember(message.get("text")))
                elif kind == "instruction_save":
                    self.emit(kind, request_id, self.instructions.save(message.get("text")))
                elif kind == "instruction_remove":
                    self.emit(kind, request_id, self.instructions.remove(message.get("text")))
                elif kind == "settings":
                    self.emit(kind, request_id, self.config.public())
                elif kind == "save":
                    self.config.save(message.get("provider"), message.get("model", ""),
                                     message.get("key", ""), message.get("clearKey", False))
                    self.emit(kind, request_id, self.config.public())
                elif kind == "generate":
                    if not self.selection:
                        raise DesktopError("Select some text and reopen the panel first.")
                    prompt = message.get("prompt", "")
                    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 8000:
                        raise DesktopError("Enter an instruction, up to 8,000 characters.")
                    credentials = self.config.credentials()
                    self.generation += 1
                    self.result = ""
                    threading.Thread(target=self.rewrite, args=(request_id, self.generation, credentials,
                                                                prompt, self.selection.text), daemon=True).start()
                elif kind == "cancel":
                    self.generation += 1
                    self.emit(kind, request_id)
                elif kind == "copy":
                    if not self.result:
                        raise DesktopError("Generate a result first.")
                    copy(self.result)
                    self.emit(kind, request_id)
                elif kind == "replace":
                    if not self.selection or not self.result:
                        raise DesktopError("Generate a result first.")
                    self.selection.replace(self.result)
                    self.emit(kind, request_id)
                else:
                    raise DesktopError("Unknown request.")
            except (DesktopError, ProviderError, InstructionError, ValueError, OSError) as exc:
                self.emit(kind, request_id, error=str(exc))


def main():
    backend = Backend()
    backend.emit("ready", data=backend.config.public())
    backend.handle({"type": "instructions"})
    for line in sys.stdin:
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError()
            backend.handle(message)
        except (ValueError, TypeError):
            backend.emit("error", error="Invalid request.")


if __name__ == "__main__":
    main()
