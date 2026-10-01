import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch, Mock
import urllib.error

import providers as p


RESPONSES = {
    "openai": {"status": "completed", "output": [
        {"type": "reasoning", "summary": []},
        {"type": "message", "role": "assistant", "status": "completed",
         "content": [{"type": "output_text", "text": " edited\n"}]}]},
    "claude": {"stop_reason": "end_turn", "content": [
        {"type": "thinking", "thinking": "private"}, {"type": "text", "text": " edited\n"}]},
    "google": {"candidates": [{"finishReason": "STOP", "content": {"parts": [
        {"thought": True, "text": "private"}, {"text": " edited\n"}]}}]},
    "cursor": {"type": "result", "subtype": "success", "is_error": False, "result": " edited\n"},
}


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "config/settings.json"
        self.store = p.ConfigStore(self.path)

    def test_defaults_and_secret_lifecycle(self):
        self.assertEqual(self.store.public()["provider"], "openai")
        self.assertEqual(set(self.store.public()["providers"]), set(p.DEFAULT_MODELS))
        result = self.store.save("openai", "test-model", "secret-api-key")
        self.assertNotIn("secret-api-key", json.dumps(result))
        self.assertTrue(result["providers"]["openai"]["hasKey"])
        self.store.save("openai", "next-model")
        self.assertEqual(self.store.credentials()["key"], "secret-api-key")
        self.store.save("claude", "claude-model", "other-secret")
        self.assertEqual(self.store.credentials("openai")["key"], "secret-api-key")
        self.store.save("openai", "next-model", clear_key=True)
        self.assertEqual(self.store.credentials()["key"], "")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_corrupt_config_has_clean_error(self):
        self.path.parent.mkdir()
        for value in ('secret-api-key', '[]', '{"provider": [], "providers": {}}'):
            self.path.write_text(value)
            with self.assertRaises(p.ProviderError) as error:
                self.store.public()
            self.assertNotIn("secret-api-key", str(error.exception))

    def test_validation(self):
        for args in [("nope", "model", ""), ("openai", "", ""), ("openai", "model", "bad\nkey")]:
            with self.assertRaises(p.ProviderError):
                self.store.save(*args)
        self.assertFalse(self.path.exists())

    def test_atomic_failure_preserves_original(self):
        self.store.save("openai", "model", "old-key")
        with patch.object(p.os, "replace", side_effect=OSError("secret-api-key")):
            with self.assertRaises(p.ProviderError) as error:
                self.store.save("openai", "model", "new-key")
        self.assertNotIn("secret-api-key", str(error.exception))
        self.assertEqual(self.store.credentials()["key"], "old-key")
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])


class ProviderTests(unittest.TestCase):
    def credentials(self, provider):
        return {"provider": provider, "model": p.DEFAULT_MODELS[provider], "key": "secret-api-key"}

    def test_http_requests_and_parsing(self):
        for provider in ("openai", "claude", "google"):
            with self.subTest(provider=provider):
                response = io.BytesIO(json.dumps(RESPONSES[provider]).encode())
                opener = Mock()
                opener.open.return_value = response
                with patch.object(p.urllib.request, "build_opener", return_value=opener):
                    self.assertEqual(p.generate(self.credentials(provider), "Improve", "source"), " edited\n")
                request = opener.open.call_args.args[0]
                self.assertEqual(opener.open.call_args.kwargs["timeout"], p.TIMEOUT)
                body = json.loads(request.data)
                self.assertNotIn("secret-api-key", request.full_url)
                self.assertNotIn("secret-api-key", request.data.decode())
                self.assertNotIn("tools", body)
                if provider == "openai":
                    self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
                    self.assertFalse(body["store"])
                    self.assertEqual(json.loads(body["input"]), {"instruction": "Improve", "source_text": "source"})
                    self.assertEqual(request.get_header("Authorization"), "Bearer secret-api-key")
                elif provider == "claude":
                    self.assertEqual(request.full_url, "https://api.anthropic.com/v1/messages")
                    self.assertEqual(body["messages"][0]["role"], "user")
                    self.assertEqual(request.get_header("Anthropic-version"), "2023-06-01")
                else:
                    self.assertTrue(request.full_url.endswith(":generateContent"))
                    self.assertEqual(body["contents"][0]["role"], "user")
                    self.assertEqual(request.get_header("X-goog-api-key"), "secret-api-key")

    def test_rejects_partial_blocked_and_malformed(self):
        for provider in RESPONSES:
            for malformed in ({}, [], {"output": None}):
                with self.subTest(provider=provider, data=malformed):
                    with self.assertRaises(p.ProviderError):
                        p._final(provider, malformed)
        cases = [
            ("openai", {**RESPONSES["openai"], "status": "incomplete"}),
            ("claude", {**RESPONSES["claude"], "stop_reason": "max_tokens"}),
            ("claude", {**RESPONSES["claude"], "stop_reason": "refusal"}),
            ("google", {"candidates": [{"finishReason": "MAX_TOKENS"}]}),
            ("google", {**RESPONSES["google"], "promptFeedback": {"blockReason": "SAFETY"}}),
            ("cursor", {**RESPONSES["cursor"], "is_error": True}),
            ("cursor", {**RESPONSES["cursor"], "result": "  "}),
        ]
        for provider, data in cases:
            with self.subTest(provider=provider, data=data), self.assertRaises(p.ProviderError):
                p._final(provider, data)

    def test_network_errors_never_echo_secrets(self):
        for code in (400, 401, 403, 404, 429, 500, 302):
            error = urllib.error.HTTPError("https://example.com/secret-api-key", code, "secret-api-key", {}, io.BytesIO(b"secret-api-key"))
            with patch.object(p.urllib.request, "build_opener") as build:
                build.return_value.open.side_effect = error
                with self.assertRaises(p.ProviderError) as caught:
                    p.generate(self.credentials("openai"), "Edit", "source")
                self.assertNotIn("secret-api-key", str(caught.exception))
        with patch.object(p.urllib.request, "build_opener") as build:
            build.return_value.open.side_effect = OSError("secret-api-key")
            with self.assertRaises(p.ProviderError) as caught:
                p.generate(self.credentials("openai"), "Edit", "source")
            self.assertNotIn("secret-api-key", str(caught.exception))

    def test_size_json_and_missing_key(self):
        for raw in (b"not json", b"[]", b"\xff", b"x" * (p.MAX_RESPONSE + 1)):
            with patch.object(p.urllib.request, "build_opener") as build:
                build.return_value.open.return_value = io.BytesIO(raw)
                with self.assertRaises(p.ProviderError):
                    p.generate(self.credentials("openai"), "Edit", "source")
        with patch.object(p, "_post") as post:
            with self.assertRaises(p.ProviderError):
                p.generate({**self.credentials("openai"), "key": ""}, "Edit", "source")
            post.assert_not_called()

    def test_no_redirect_credentials(self):
        self.assertIsNone(p._NoRedirect().redirect_request(None, None, 302, "", {}, "https://attacker.test"))

    def test_cursor_stdin_permissions_and_environment(self):
        def start(command, **kwargs):
            self.assertNotIn("secret-api-key", command)
            self.assertNotIn("source", command)
            self.assertIn("--trust", command)
            self.assertNotIn("--force", command)
            self.assertEqual(command[command.index("--mode") + 1], "ask")
            self.assertEqual(command[command.index("--sandbox") + 1], "enabled")
            config = json.loads((Path(kwargs["cwd"]) / ".cursor/cli.json").read_text())
            self.assertIn("Shell(*)", config["permissions"]["deny"])
            self.assertIn("Mcp(*:*)", config["permissions"]["deny"])
            self.assertEqual(kwargs["env"]["CURSOR_API_KEY"], "secret-api-key")
            self.assertNotIn("CURSOR_API_ENDPOINT", kwargs["env"])
            kwargs["stdout"].write(json.dumps(RESPONSES["cursor"]).encode())
            process = Mock(returncode=0)
            process.communicate.side_effect = lambda **kw: self.assertIn(b"source", kw["input"])
            return process
        with patch.object(p, "_cursor_path", return_value="/bin/cursor-agent"), patch.object(p.subprocess, "Popen", side_effect=start):
            self.assertEqual(p.generate(self.credentials("cursor"), "Edit", "source"), " edited\n")

    def test_cursor_missing_failure_and_timeout(self):
        with patch.object(p, "_cursor_path", return_value=None), self.assertRaisesRegex(p.ProviderError, "Install Cursor"):
            p.generate(self.credentials("cursor"), "Edit", "source")
        for timeout in (False, True):
            process = Mock(returncode=1)
            if timeout:
                process.communicate.side_effect = [subprocess.TimeoutExpired("secret-api-key", 1), None]
            with patch.object(p, "_cursor_path", return_value="cursor-agent"), patch.object(p.subprocess, "Popen", return_value=process), patch.object(p.os, "killpg") as kill:
                with self.assertRaises(p.ProviderError) as caught:
                    p.generate(self.credentials("cursor"), "Edit", "source")
                self.assertNotIn("secret-api-key", str(caught.exception))
                if timeout:
                    kill.assert_called_once_with(process.pid, p.signal.SIGKILL)


if __name__ == "__main__":
    unittest.main()
