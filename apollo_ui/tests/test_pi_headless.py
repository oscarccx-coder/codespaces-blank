"""Hardware-free headless Pi Apollo tests (also run on Linux ARM64 CI)."""
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from apollo_pi import PiAssistant, handler_factory, main
from pi.update_pi import import_key, can_apply_update
from apollo_update import UpdateService


class PiAssistantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "config.json").write_text(json.dumps({
            "version": "1.0.0", "model": "desktop-unused-model",
            "ollama_url": "http://127.0.0.1:11434", "database": "apollo_memory.db",
        }), encoding="utf-8")
        self.ai = PiAssistant(self.root, model="test-pi:small")

    def test_small_model_and_no_automatic_tools(self):
        self.assertEqual(self.ai.client.model, "test-pi:small")
        with patch.object(self.ai.client, "models", return_value=["test-pi:small"]), \
             patch.object(self.ai.client, "chat_once",
                          return_value={"message": {"content": "Locally generated reply"}}) as called:
            answer = self.ai.ask("Hello Pi")
            self.assertEqual(answer["source"], "local-ollama")
            self.assertEqual(answer["answer"], "Locally generated reply")
            messages = called.call_args.args[0]
            self.assertEqual(messages[-1]["content"], "Hello Pi")
            self.assertIn("cannot make autonomous treatment", messages[0]["content"])
            self.assertIsNone(called.call_args.kwargs.get("tools"))
        self.assertEqual(self.ai.memory.stats()["conversations"], 1)

    def test_no_wrong_model_fallback(self):
        with patch.object(self.ai.client, "models", return_value=["other-model"]):
            with self.assertRaisesRegex(Exception, "not installed"):
                self.ai.ask("Should not execute")
        self.assertEqual(self.ai.memory.stats()["conversations"], 0)

    def test_reject_long_or_empty_message(self):
        for message in ("", " ", "x" * 4001, None, {"message": "hi"}):
            with self.subTest(type=type(message)), self.assertRaises(ValueError):
                self.ai.ask(message)

    def test_token_file_private_and_persistent(self):
        path = self.ai.token_path
        self.assertTrue(path.is_file())
        if os.name != "nt":
            self.assertEqual(path.stat().st_mode & 0o077, 0)
        self.assertEqual(PiAssistant(self.root).token, self.ai.token)
        self.assertNotIn("token", self.ai.health())

    def test_http_token_auth_and_input_bounds(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(self.ai))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}"
        with self.assertRaises(urllib.error.HTTPError) as no_auth:
            urllib.request.urlopen(url + "/health", timeout=3)
        self.assertEqual(no_auth.exception.code, 401)
        headers = {"Authorization": "Bearer " + self.ai.token, "Content-Type": "application/json"}
        with urllib.request.urlopen(
            urllib.request.Request(url + "/health", headers=headers), timeout=3
        ) as reply:
            payload = json.load(reply)
        self.assertEqual(payload["mode"], "pi-headless")
        bad = urllib.request.Request(url + "/chat", headers=headers, method="POST",
                                     data=b'{"message":""}')
        with self.assertRaises(urllib.error.HTTPError) as invalid:
            urllib.request.urlopen(bad, timeout=3)
        self.assertEqual(invalid.exception.code, 400)
        with patch.object(self.ai.client, "models", return_value=["test-pi:small"]), \
             patch.object(self.ai.client, "chat_once",
                          return_value={"message": {"content": "Apollo Pi online"}}):
            good = urllib.request.Request(url + "/chat", headers=headers, method="POST",
                                          data=b'{"message":"ping"}')
            with urllib.request.urlopen(good, timeout=3) as reply:
                self.assertEqual(json.load(reply)["answer"], "Apollo Pi online")

    def test_reject_public_bind_even_in_self_test(self):
        with self.assertRaises(SystemExit):
            main(["--base", str(self.root), "--bind", "0.0.0.0", "--self-test"])

    def test_signed_update_requires_explicit_stopped_service(self):
        with patch.dict(os.environ, {}, clear=True):
            ok, message = can_apply_update()
        self.assertFalse(ok)
        self.assertIn("update_pi.sh", message)

    def test_key_fingerprint_must_match_before_trusting(self):
        key = self.root / "dummy.pem"
        key.write_text("test-only", encoding="utf-8")
        updater = UpdateService(self.root)
        with self.assertRaises(ValueError):
            import_key(updater, key, "0" * 64)
        self.assertFalse(updater.public_key_path.exists())


if __name__ == "__main__":
    unittest.main()
