"""Offline VoiceStudio bridge tests; no models, audio devices or real API required."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from apollo_voicestudio import _endpoint, probe, list_voices, transcribe, synthesize, create_clone
from apollo_voicestudio_runtime import _validate_checkout
from apollo_capabilities import CapabilityService


def fake_wav():
    data = io.BytesIO()
    with wave.open(data, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 800)
    return data.getvalue()


class VoiceServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        test = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                if self.path == "/health":
                    content = json.dumps({"status": "ok", "device": "cpu", "version": "local-test"}).encode()
                elif self.path == "/v1/audio/voices":
                    content = json.dumps({"voices": [{"voice_id": "user123", "name": "Apollo"}],
                                          "engines": [{"id": "omnivoice", "name": "OmniVoice"}]}).encode()
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            def do_POST(self):
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                test.posted.append((self.path, raw, self.headers.get("Content-Type")))
                if self.path == "/v1/audio/speech":
                    content, mime = fake_wav(), "audio/wav"
                elif self.path == "/v1/audio/transcriptions":
                    content, mime = b'{"text":"Apollo heard you"}', "application/json"
                elif self.path == "/profiles":
                    content, mime = b'{"id":"clone0001","name":"My Voice"}', "application/json"
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
        self.posted = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def test_health_and_voices(self):
        self.assertEqual(probe(self.base)["device"], "cpu")
        names = list_voices(self.base)
        self.assertEqual(names["voices"][0]["voice_id"], "user123")
        self.assertEqual(names["engines"][0]["id"], "omnivoice")

    def test_wav_generation(self):
        output = self.root / "Apollo.wav"
        result = synthesize(self.base, "Hello there", output, voice="user123", model="omnivoice")
        self.assertTrue(result["saved"])
        self.assertGreater(result["seconds"], 0)
        self.assertTrue(output.is_file())
        self.assertEqual(self.posted[0][0], "/v1/audio/speech")
        body = json.loads(self.posted[0][1])
        self.assertEqual(body["voice"], "user123")
        self.assertEqual(body["response_format"], "wav")

    def test_transcription(self):
        file = self.root / "sample.wav"
        file.write_bytes(fake_wav())
        result = transcribe(self.base, file, language="en-GB")
        self.assertEqual(result, "Apollo heard you")
        self.assertIn(b'name="file"', self.posted[0][1])
        self.assertIn(b'name="language"', self.posted[0][1])

    def test_authorized_clone(self):
        file = self.root / "reference.wav"
        file.write_bytes(fake_wav() * 8)
        with self.assertRaises(PermissionError):
            create_clone(self.base, file, "My Voice")
        self.assertEqual(create_clone(self.base, file, "My Voice",
                                      consent_confirmed=True)["id"], "clone0001")
        self.assertIn(b'name="ref_audio"', self.posted[0][1])
        self.assertIn(b'name="kind"', self.posted[0][1])

    def test_external_network_and_wrong_paths_rejected(self):
        for url in ("https://127.0.0.1:3900", "http://example.com:3900",
                    "http://127.0.0.1:3900@evil.invalid:3900",
                    "http://127.0.0.1:3900/unsafe"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                _endpoint(url, "/health")
        with self.assertRaises(ValueError):
            synthesize(self.base, "", self.root / "none.wav")
        self.assertFalse((self.root / "none.wav").exists())


class ApolloRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.svc = CapabilityService(self.root)

    def test_config_and_selection(self):
        self.svc.configure(voice="voicestudio", transcription="voicestudio",
                           voicestudio_url="http://127.0.0.1:3900",
                           voicestudio_voice="user123", voicestudio_model="tts-1")
        self.assertEqual(self.svc.settings()["voice"], "voicestudio")
        with self.assertRaises(ValueError):
            self.svc.configure(voicestudio_url="http://1.2.3.4:3900")
        with self.assertRaises(ValueError):
            self.svc.configure(voicestudio_voice="")

    def test_existing_speech_module_uses_voicestudio_without_xtts(self):
        from modules.text_to_speech.module import Module
        speech = Module({"base_dir": self.root})
        self.svc.configure(voice="voicestudio", transcription="voicestudio")
        with patch("apollo_capabilities.service", return_value=self.svc), \
             patch.object(speech, "_require_windows"), \
             patch.object(speech, "_queue_voice_imprint",
                          return_value={"started": True}) as queue:
            response = speech.run("speak_text", {"text": "Test voice"})
            self.assertEqual(response["engine"], "VoiceStudio")
            queue.assert_called_once_with("Test voice", backend="voicestudio")
        with patch("apollo_capabilities.service", return_value=self.svc), \
             patch("apollo_voicestudio.transcribe", return_value="recognized") as asr:
            self.assertEqual(speech._recognize_wave_file(self.root / "dummy.wav"), "recognized")
            self.assertTrue(asr.called)

    def test_prepare_runs_only_pinned_commands_in_selected_checkout(self):
        from unittest.mock import Mock
        from apollo_voicestudio_runtime import prepare_backend
        folder = self.root / "VoiceStudio"
        (folder / "scripts").mkdir(parents=True)
        (folder / "backend").mkdir()
        (folder / "backend" / "main.py").write_text("pass")
        (folder / "scripts" / "dev-backend.mjs").write_text("")
        (folder / "package.json").write_text(json.dumps({
            "name": "omnivoice-studio-monorepo",
            "scripts": {"dev:api": "bun scripts/dev-backend.mjs"},
        }))
        with patch("apollo_voicestudio_runtime.shutil.which", side_effect=lambda name: name), \
             patch("apollo_voicestudio_runtime.subprocess.run", return_value=Mock(returncode=0)) as runner:
            outcome = prepare_backend(folder, self.root / "logs")
            self.assertTrue(outcome["prepared"])
            self.assertEqual(runner.call_count, 2)
            self.assertEqual(runner.call_args_list[0].args[0], ["bun", "install", "--frozen-lockfile"])
            self.assertEqual(runner.call_args_list[1].args[0], ["bun", "run", "setup:api"])
            self.assertEqual(runner.call_args_list[0].kwargs["cwd"], str(folder))

    def test_auto_detect_uses_downloaded_source_without_copying(self):
        from apollo_voicestudio_runtime import find_downloaded_checkout
        install = self.root / "Apollo" / "apollo 1" / "apollo_ui"
        install.mkdir(parents=True)
        downloaded = self.root / "Apollo" / "VoiceStudio" / "VoiceStudio-main"
        (downloaded / "scripts").mkdir(parents=True)
        (downloaded / "backend").mkdir()
        (downloaded / "backend" / "main.py").write_text("pass")
        (downloaded / "scripts" / "dev-backend.mjs").write_text("")
        (downloaded / "package.json").write_text(json.dumps({
            "name": "omnivoice-studio-monorepo",
            "scripts": {"dev:api": "bun scripts/dev-backend.mjs"},
        }))
        self.assertEqual(find_downloaded_checkout(install), str(downloaded.resolve()))
        self.assertEqual(find_downloaded_checkout(install, str(downloaded)), str(downloaded.resolve()))
        self.assertFalse((install / "VoiceStudio").exists())
        (downloaded / "package.json").write_text(json.dumps({"name": "unrelated-project"}))
        self.assertEqual(find_downloaded_checkout(install), "")

    def test_checkout_requires_matching_upstream_entrypoint(self):
        folder = self.root / "VoiceStudio"
        (folder / "scripts").mkdir(parents=True)
        (folder / "backend").mkdir()
        (folder / "backend" / "main.py").write_text("pass")
        (folder / "scripts" / "dev-backend.mjs").write_text("")
        (folder / "package.json").write_text(json.dumps({
            "name": "omnivoice-studio-monorepo",
            "scripts": {"dev:api": "bun scripts/dev-backend.mjs"},
        }))
        self.assertEqual(_validate_checkout(folder), folder.resolve())
        with self.assertRaises(ValueError):
            self.svc.configure(voicestudio_checkout=str(self.root))


if __name__ == "__main__":
    unittest.main()
