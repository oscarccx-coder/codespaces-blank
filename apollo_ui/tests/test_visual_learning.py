"""Visual Lab contract tests: no real camera, network or model required."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_FILE = ROOT / "modules" / "visual_learning" / "module.py"
spec = importlib.util.spec_from_file_location("apollo_visual_lab_test", MODULE_FILE)
vision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vision)


class StubResponse:
    headers = {"Content-Type": "image/jpeg"}

    def __init__(self, data):
        self.raw = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, amount):
        return self.raw[:amount]


class VisionTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.module = vision.Module({"base_dir": self.root.name})
        self.jpg = b"\xff\xd8\xff" + b"test-image-payload"

    def _image(self):
        return self.module._store(self.jpg, "file:test.jpg")

    def test_self_test_without_devices_or_internet(self):
        self.assertIn("passed", self.module.self_test())
        self.assertTrue((self.module.folder).exists())

    def test_reject_fake_images_and_oversized(self):
        with self.assertRaisesRegex(ValueError, "Only real"):
            self.module._store(b"not-image", "test")
        with self.assertRaisesRegex(ValueError, "under 8 MB"):
            self.module._store(b"\xff\xd8\xff" + b"x" * vision.MAX_IMAGE_BYTES, "test")

    def test_only_stored_image_ids_are_readable_by_tools(self):
        stored = self._image()
        self.assertEqual(self.module._image_path(stored["image_id"]).read_bytes(), self.jpg)
        for attempt in ("../../secret.png", "/etc/passwd", "C:\\Users\\user\\private.jpg", "sample.jpg"):
            with self.subTest(image_id=attempt), self.assertRaises(ValueError):
                self.module.run("analyse_image", {"image_id": attempt})
        with self.assertRaises(FileNotFoundError):
            self.module._image_path("a" * 20 + ".jpg")

    def test_local_import_needs_ui_method_not_tool(self):
        with self.assertRaises(KeyError):
            self.module.run("import_image", {"path": "/etc/passwd"})
        sample = Path(self.root.name) / "chosen.jpg"
        sample.write_bytes(self.jpg)
        self.assertEqual(self.module.import_image(sample)["image_id"], self._image()["image_id"])

    def test_ssrf_protection_and_redirects(self):
        for url in (
            "http://example.com/image.png",
            "file:///etc/passwd",
            "https://127.0.0.1/camera.jpg",
            "https://192.168.1.1/photo.jpg",
            "https://user:password@example.com/photo.jpg",
            "https://example.com:8443/image.jpg",
            "https://localhost/photo.jpg",
        ):
            with self.subTest(url=url), self.assertRaises((ValueError, PermissionError)):
                vision._public_image_url(url)
        with mock.patch.object(vision.socket, "getaddrinfo", return_value=[
            (2, 1, 0, "", ("10.0.0.3", 443))]):
            with self.assertRaises(PermissionError):
                vision._public_image_url("https://bad.example/camera.png")

    def test_model_payload_is_local_only_and_note_is_searchable(self):
        image = self._image()
        captured = {}

        def fake_open(request, timeout):
            captured["url"] = request.full_url
            captured["payload"] = json.loads(request.data)
            return StubResponse(json.dumps({
                "message": {"content": "I can see a small printed circuit board."}
            }).encode())

        with mock.patch.object(vision.urllib.request, "urlopen", side_effect=fake_open):
            result = self.module.analyse_image(image["image_id"], "What do you see?")
        self.assertEqual(captured["url"], "http://127.0.0.1:11434/api/chat")
        self.assertEqual(captured["payload"]["model"], vision.DEFAULT_MODEL)
        self.assertEqual(len(captured["payload"]["messages"][0]["images"]), 1)
        self.assertIn("circuit board", result["analysis"])
        saved = self.module.save_visual_note(image["image_id"], "Arduino circuit")
        note = Path(saved["path"]).read_text(encoding="utf-8")
        self.assertIn("Arduino circuit", note)
        self.assertIn("Unverified", note)
        self.assertIn("circuit board", note)
        self.assertIn("storage", saved["path"])

    def test_cannot_save_unanalysed_image(self):
        with self.assertRaisesRegex(ValueError, "Analyse"):
            self.module.save_visual_note(self._image()["image_id"], "Electronics")

    def test_web_image_import_limits_and_content_type(self):
        with mock.patch.object(vision, "_public_image_url", return_value="https://example.com/pic.jpg"):
            with mock.patch.object(vision.urllib.request, "build_opener") as factory:
                factory.return_value.open.return_value = StubResponse(self.jpg)
                result = self.module.fetch_online_image("https://example.com/pic.jpg")
        self.assertEqual(result["source"], "https://example.com/pic.jpg")
        self.assertTrue(Path(result["path"]).exists())

    def test_research_requires_real_source_module(self):
        image = self._image()
        self.module._analyses[image["image_id"]] = {
            "image_id": image["image_id"], "source": "file:test",
            "model": "stub", "question": "q", "analysis": "observation",
            "analysed_at": "now",
        }
        with self.assertRaisesRegex(RuntimeError, "Research & Training"):
            self.module.research_image(image["image_id"], "board wiring")

    def test_chat_camera_tool_requires_high_risk_gate(self):
        from apollo_runtime import ApolloRuntime
        runtime = ApolloRuntime(self.root.name)
        try:
            self.assertEqual(runtime.risk_for("visual_learning__capture_camera"), "high")
            self.assertEqual(runtime.get_permission("visual_learning__capture_camera"), "deny")
        finally:
            runtime.conn.close()


if __name__ == "__main__":
    unittest.main()
