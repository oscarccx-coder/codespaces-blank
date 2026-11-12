"""Chat persistence, scoped sources, real exports, streaming and Qt interactions."""
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from apollo_chat_store import ChatStore
from apollo_chat_files import extract_attachment, build_chat_context, table_summary, export_canvas, MAX_FILE
from ollama_client import OllamaClient


def attachment(name="notes.txt", text="Known measurement", kind="text", image=""):
    return {"name": name, "content": text, "kind": kind, "sha256": name + text,
            "size": len(text), "image": image}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = ChatStore(self.tmp.name); self.addCleanup(self.store.close)
        self.chat = self.store.new_chat()

    def test_distinct_search_pin_archive_and_delete(self):
        second = self.store.new_chat("Second topic")
        self.store.add_message(self.chat, "user", "Unique physics question")
        self.store.add_message(second, "user", "Other content")
        self.assertEqual([c["id"] for c in self.store.list_chats("physics")], [self.chat])
        self.assertEqual(self.store.list_chats("%_literal"), [])
        self.store.update_chat(self.chat, pinned=1)
        self.assertEqual(self.store.list_chats()[0]["id"], self.chat)
        self.store.update_chat(self.chat, archived=1)
        self.assertEqual([c["id"] for c in self.store.list_chats(archived=True)], [self.chat])
        self.store.delete_chat(self.chat)
        self.assertEqual(self.store.messages(self.chat), [])

    def test_project_sources_and_instructions_are_scoped(self):
        a = self.store.create_project("Apollo", "Use measured evidence")
        b = self.store.create_project("Private other project", "UNRELATED INSTRUCTION")
        self.store.update_chat(self.chat, project_id=a)
        self.store.add_attachment(attachment("hardware.txt", "Apollo hardware budget"), project_id=a)
        self.store.add_attachment(attachment("secret.txt", "UNRELATED SECRET"), project_id=b)
        self.store.add_message(self.chat, "user", "hardware budget")
        packet = build_chat_context(self.store, self.chat, "hardware budget")
        text = json.dumps(packet)
        self.assertIn("Use measured evidence", text)
        self.assertIn("Apollo hardware budget", text)
        self.assertNotIn("UNRELATED", text)

    def test_unrelated_chats_are_not_recalled(self):
        other = self.store.new_chat()
        self.store.add_message(other, "user", "PRIVATE UNIQUE IN ANOTHER CHAT")
        self.store.add_message(self.chat, "user", "Hello")
        packet = build_chat_context(self.store, self.chat, "Hello")
        self.assertNotIn("PRIVATE UNIQUE", json.dumps(packet))
        self.assertEqual(sum(m["content"] == "Hello" for m in packet["messages"]), 1)

    def test_context_budget_omits_old_turns_and_labels_truncation(self):
        self.store.add_message(self.chat, "user", "old " * 10000)
        self.store.add_message(self.chat, "assistant", "old answer " * 10000)
        self.store.add_message(self.chat, "user", "Current question")
        packet = build_chat_context(self.store, self.chat, "Current question", max_chars=6000)
        self.assertLessEqual(packet["characters"], 6000)
        self.assertTrue(packet["warnings"])
        self.assertEqual(packet["messages"][-1]["content"], "Current question")

    def test_failed_and_stopped_replies_are_not_presented_as_complete_context(self):
        self.store.add_message(self.chat, "assistant", "FAILED ASSERTION", "failed")
        self.store.add_message(self.chat, "assistant", "STOPPED ASSERTION", "stopped")
        self.store.add_message(self.chat, "user", "Current")
        packet = build_chat_context(self.store, self.chat, "Current")
        self.assertNotIn("ASSERTION", json.dumps(packet))

    def test_draft_canvas_settings_and_interruption_survive_restart(self):
        self.store.update_chat(self.chat, draft="Unsent text", canvas="Local draft", model="my-model", style="Detailed")
        ident = self.store.add_message(self.chat, "assistant", "Partial answer", "streaming")
        reopened = ChatStore(self.tmp.name)
        try:
            self.assertEqual(reopened.chat(self.chat)["draft"], "Unsent text")
            self.assertEqual(reopened.chat(self.chat)["canvas"], "Local draft")
            self.assertEqual(reopened.chat(self.chat)["model"], "my-model")
            self.assertEqual(reopened.messages(self.chat)[0]["status"], "interrupted")
            self.assertEqual(reopened.messages(self.chat)[0]["id"], ident)
        finally:
            reopened.close()

    def test_branch_preserves_original_and_excludes_future_sources(self):
        a = self.store.add_attachment(attachment("first.txt", "FIRST"), chat_id=self.chat)
        first = self.store.add_message(self.chat, "user", "Original question", metadata={"attachments": [a]})
        self.store.add_message(self.chat, "assistant", "Original answer")
        later = self.store.add_attachment(attachment("later.txt", "FUTURE"), chat_id=self.chat)
        self.store.add_message(self.chat, "user", "Later", metadata={"attachments": [later]})
        branch = self.store.branch(self.chat, first)
        self.assertEqual(len(self.store.messages(self.chat)), 3)
        self.assertEqual(self.store.messages(branch), [])
        files = self.store.attachments(chat_id=branch)
        self.assertEqual([f["name"] for f in files], ["first.txt"])

    def test_branch_maps_retained_attachment_references(self):
        ident = self.store.add_attachment(attachment(), chat_id=self.chat)
        self.store.add_message(self.chat, "user", "First", metadata={"attachments": [ident]})
        second = self.store.add_message(self.chat, "user", "Second")
        branch = self.store.branch(self.chat, second)
        copied = self.store.messages(branch)[0]["metadata"]["attachments"][0]
        self.assertNotEqual(copied, ident)
        self.assertEqual(self.store.attachment(copied)["chat_id"], branch)

    def test_memory_toggle_and_reference_source_packet(self):
        self.store.add_message(self.chat, "user", "Question")
        memory = {"text": "[memory:7] Motor notes\nSource: Owner\nMeasured current is 2 A."}
        packet = build_chat_context(self.store, self.chat, "Question", memory_packet=memory)
        self.assertIn("2 A", json.dumps(packet))
        self.assertEqual(packet["sources"][0]["id"], "memory:7")
        self.store.update_chat(self.chat, memory=0)
        self.assertNotIn("2 A", json.dumps(build_chat_context(self.store, self.chat, "Question", memory_packet=memory)))

    def test_image_input_is_preserved_for_followup(self):
        image_id = self.store.add_attachment(attachment("photo.png", "", "image", "BASE64IMAGE"), chat_id=self.chat)
        self.store.add_message(self.chat, "user", "What is this?", metadata={"attachments": [image_id]})
        current = build_chat_context(self.store, self.chat, "What is this?")
        self.assertEqual(current["messages"][-1]["images"], ["BASE64IMAGE"])
        self.store.add_message(self.chat, "assistant", "A test photo")
        self.store.add_message(self.chat, "user", "What colour?")
        followup = build_chat_context(self.store, self.chat, "What colour?")
        self.assertTrue(any(m.get("images") == ["BASE64IMAGE"] for m in followup["messages"]))

    def test_temporary_store_never_creates_files_and_forces_no_tools_memory(self):
        root = Path(self.tmp.name) / "temporary-only"
        temporary = ChatStore(root, temporary=True)
        try:
            chat = temporary.new_chat()
            temporary.update_chat(chat, tools=1, memory=1)
            temporary.add_message(chat, "user", "Temporary material")
            temporary.add_attachment(attachment(), chat_id=chat)
            self.assertEqual(temporary.chat(chat)["tools"], 0)
            self.assertEqual(temporary.chat(chat)["memory"], 0)
            self.assertFalse(root.exists())
        finally:
            temporary.close()

    def test_delete_removes_attachment_and_message_records(self):
        ident = self.store.add_attachment(attachment(), chat_id=self.chat)
        self.store.add_message(self.chat, "user", "Test")
        self.store.delete_chat(self.chat)
        with self.assertRaises(KeyError):
            self.store.attachment(ident)
        self.assertEqual(self.store.messages(self.chat), [])

    def test_legacy_import_is_once_and_original_data_is_not_required(self):
        data = [{"role": "user", "content": "Old question"}, {"role": "assistant", "content": "Old answer"}]
        imported = self.store.import_legacy(data)
        self.assertEqual(len(self.store.messages(imported)), 2)
        self.assertIsNone(self.store.import_legacy(data))

    def test_export_omits_image_binary(self):
        self.store.add_attachment(attachment("photo.png", "", "image", "DO_NOT_EXPORT_IMAGE_BYTES"), chat_id=self.chat)
        self.store.add_message(self.chat, "user", "Export this")
        exported = self.store.export(self.chat, "json")
        self.assertNotIn("DO_NOT_EXPORT_IMAGE_BYTES", exported)
        self.assertIn("Export this", self.store.export(self.chat))

    def test_unsent_attachment_is_not_in_model_context(self):
        self.store.add_attachment(attachment("draft.txt", "UNSENT PRIVATE MATERIAL"), chat_id=self.chat)
        self.store.add_message(self.chat, "user", "Hi")
        self.assertNotIn("UNSENT PRIVATE MATERIAL", json.dumps(build_chat_context(self.store, self.chat, "Hi")))


class FileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_text_snapshot_and_actual_csv_statistics(self):
        path = self.root / "data.csv"; path.write_text("Name,Value\nA,2\nB,4\nC,6\n")
        data = extract_attachment(path)
        summary = table_summary(data)
        self.assertEqual(summary["rows"], 3)
        self.assertEqual(summary["columns"][1]["sum"], 12)
        self.assertEqual(summary["columns"][1]["mean"], 4)
        path.write_text("Changed")
        self.assertIn("A,2", data["content"])

    def test_size_extension_binary_and_text_limits(self):
        big = self.root / "big.txt"
        with big.open("wb") as handle:
            handle.truncate(MAX_FILE + 1)
        with self.assertRaises(ValueError): extract_attachment(big)
        binary = self.root / "bad.txt"; binary.write_bytes(b"hello\0world")
        with self.assertRaises(ValueError): extract_attachment(binary)
        exe = self.root / "app.exe"; exe.write_bytes(b"test")
        with self.assertRaises(ValueError): extract_attachment(exe)
        text = self.root / "long.txt"; text.write_text("x" * 100000)
        result = extract_attachment(text)
        self.assertEqual(len(result["content"]), 80000)
        self.assertIn("truncated", result["notice"])

    def test_docx_read_and_real_export(self):
        try:
            from docx import Document
        except ImportError:
            self.skipTest("python-docx not installed")
        path = self.root / "notes.docx"
        export_canvas(path, "# Experiment\nMeasured force: 4 N\n```python\nprint(4)\n```")
        result = extract_attachment(path)
        self.assertIn("Measured force: 4 N", result["content"])
        self.assertEqual(Document(path).paragraphs[0].text, "Experiment")

    def test_spreadsheet_is_actual_xlsx_and_does_not_execute_cells(self):
        try:
            from openpyxl import load_workbook
        except ImportError:
            self.skipTest("openpyxl not installed")
        path = self.root / "table.xlsx"
        export_canvas(path, "Name,Value\nA,12\nB,=SOMETHING()")
        book = load_workbook(path)
        try:
            self.assertEqual(book.active["B3"].data_type, "s")
        finally:
            book.close()
        self.assertIn("12", extract_attachment(path)["content"])

    def test_pdf_export_has_selectable_text_without_qt(self):
        try:
            import reportlab
            import pypdf
        except ImportError:
            self.skipTest("PDF dependencies not installed")
        path = self.root / "result.pdf"
        export_canvas(path, "# Measured Result\nMeasured result: 42 N\n```python\nprint(42)\n```")
        content = extract_attachment(path)["content"]
        self.assertIn("Measured result: 42 N", content)
        self.assertIn("print(42)", content)


class TransportTests(unittest.TestCase):
    def start_server(self, handler):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        return "http://127.0.0.1:" + str(server.server_port)

    def test_actual_http_stream_and_metrics(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200); self.end_headers()
                self.wfile.write(b'{"message":{"content":"Hello"}}\n')
                self.wfile.write(b'{"message":{"content":" world"},"done":true,"model":"test","eval_count":2}\n')
        client = OllamaClient(self.start_server(Handler), "test"); client.strict_model = True
        self.assertEqual("".join(client.stream_chat([{"role": "user", "content": "Hi"}])), "Hello world")
        self.assertEqual(client.last_metrics["eval_count"], 2)

    def test_stop_interrupts_a_waiting_stream_socket(self):
        started, release = threading.Event(), threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200); self.end_headers()
                self.wfile.write(b'{"message":{"content":"partial"}}\n'); self.wfile.flush()
                started.set(); release.wait(5)
        client = OllamaClient(self.start_server(Handler), "test"); client.strict_model = True
        chunks = []
        def run():
            try:
                chunks.extend(client.stream_chat([{"role": "user", "content": "Hi"}]))
            except Exception:
                pass
        thread = threading.Thread(target=run); thread.start()
        try:
            self.assertTrue(started.wait(2)); client.cancel_generation(); thread.join(2)
            self.assertFalse(thread.is_alive())
        finally:
            release.set(); thread.join(6)

    def test_selected_model_is_not_silently_replaced(self):
        client = OllamaClient("http://127.0.0.1:11434", "chosen-model"); client.strict_model = True
        with patch.object(client, "models", side_effect=AssertionError("Must not auto-switch")):
            self.assertEqual(client._chat_payload([], True)["model"], "chosen-model")

    def test_actual_nonstreaming_chat_preserves_images_and_handles_errors(self):
        received = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                received.append(payload)
                self.send_response(200); self.end_headers()
                self.wfile.write(b'{"message":{"content":"A picture"},"model":"test","eval_count":3}')
        client = OllamaClient(self.start_server(Handler), "test"); client.strict_model = True
        result = client.chat_once([{"role": "user", "content": "Describe", "images": ["IMAGE"]}])
        self.assertEqual(result["message"]["content"], "A picture")
        self.assertEqual(received[0]["messages"][0]["images"], ["IMAGE"])


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QThreadPool, Qt
    from PySide6.QtWidgets import QApplication, QInputDialog, QFileDialog
    from PySide6.QtTest import QTest
    from apollo_chat_workspace import ChatWorkspace, Composer, markdown_html
except ImportError:
    QApplication = None


class FakeManager:
    def __init__(self): self.calls = []
    def get_module(self, key): return None
    def ollama_tools(self): return []


class FakeClient:
    requests = []
    def __init__(self, *args, **kwargs):
        self.model = args[1]; self.last_metrics = {}; self.stopped = False
    def model_info(self): return {"capabilities": ["completion", "vision"]}
    def stream_chat(self, messages, tools=None):
        self.requests.append(messages)
        for piece in ("# A real test reply\n", "\n```python\nprint('hello')\n```\n"):
            if self.stopped: break
            yield piece
        self.last_metrics = {"eval_count": 12}
    def cancel_generation(self): self.stopped = True


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class WorkspaceQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        class Owner:
            config = {"ollama_url": "http://127.0.0.1:11434", "model": "local-test", "num_ctx": 8192}
            chat_history = []
            def __init__(self):
                self.module_manager = FakeManager(); self.thread_pool = QThreadPool(); self.learned = []
            def start_speech_to_text(self): pass
            def toggle_speech_mute(self): pass
            def speak_apollo_reply(self, text): pass
            def _apply_integrated_chat_learning(self, text): self.learned.append(text)
        self.owner = Owner()
        self.view = ChatWorkspace(self.owner, self.tmp.name); self.view.resize(1350, 850); self.view.show()
        self.addCleanup(self.cleanup_view)
        self.client_patch = patch("apollo_chat_workspace.OllamaClient", FakeClient)
        self.client_patch.start(); self.addCleanup(self.client_patch.stop)
        FakeClient.requests = []

    def test_auto_routing_fetches_sources_preserves_model_and_tools_boundary(self):
        self.view.mode.setCurrentText('Auto'); self.view.tools_check.setChecked(True); calls=[]
        def execute(module,action,args):
            calls.append((module,action,args))
            return {'sources':[{'url':'https://example.org/paper','title':'Paper','text':'Fetched public evidence.'}], 'saved':{'saved':True,'filename':args['filename']}}
        self.owner.module_manager.execute=execute
        self.view.composer.setText('Research public source retrieval'); self.view.send(); self.pump()
        self.assertEqual(calls[0][1],'explore_web_and_save'); self.assertEqual(self.view.turn_client.model,'local-test')
        self.assertIn('Fetched public evidence',json.dumps(FakeClient.requests[-1])); self.assertTrue(any(s['id']=='https://example.org/paper' for s in self.view.packet['sources']))
        calls.clear(); self.view.tools_check.setChecked(False); self.view.composer.setText('Research public source retrieval'); self.view.send(); self.pump()
        self.assertEqual(calls,[]); self.assertIn('Tools are unavailable',self.view.activities[0]['result'])

    def cleanup_view(self):
        if self.view.busy: self.view.stop()
        self.owner.thread_pool.waitForDone(3000); self.app.processEvents()
        self.view.prepare_close(); self.view.close_store(); self.view.close()

    def pump(self):
        until = time.monotonic() + 4
        while (self.view.busy or self.view.io_busy) and time.monotonic() < until:
            self.app.processEvents(); QTest.qWait(10)
        self.app.processEvents()
        self.assertFalse(self.view.busy); self.assertFalse(self.view.io_busy)

    def test_multiline_composer_enter_and_real_saved_reply(self):
        self.view.composer.setText("Question line 1")
        QTest.keyClick(self.view.composer, Qt.Key_Return, Qt.ShiftModifier)
        QTest.keyClicks(self.view.composer, "Question line 2")
        self.assertIn("\n", self.view.composer.text())
        QTest.keyClick(self.view.composer, Qt.Key_Return)
        self.pump()
        messages = self.view.store.messages(self.view.chat_id)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[-1]["status"], "complete")
        self.assertIn("real test reply", self.view.transcript.toPlainText())
        self.assertEqual(messages[-1]["metadata"]["metrics"]["eval_count"], 12)

    def test_temporary_does_not_write_history_or_learning(self):
        initial = len(self.view.store.list_chats())
        self.view.new_chat(temporary=True)
        self.view.composer.setText("Remember this PRIVATE temporary sentence")
        self.view.send(); self.pump()
        self.assertEqual(len(self.view.store.list_chats()), initial)
        self.assertFalse(self.owner.learned)
        self.assertFalse(any("PRIVATE" in json.dumps(self.view.store.messages(c["id"])) for c in self.view.store.list_chats()))
        self.view.new_chat()
        self.assertIs(self.view.session_store, self.view.store)

    def test_restore_draft_on_first_load_does_not_erase_it(self):
        self.view.composer.setText("Keep my unsent draft"); self.view.save_draft()
        ident = self.view.chat_id
        second = ChatWorkspace(self.owner, self.tmp.name)
        try:
            self.assertEqual(second.chat_id, ident)
            self.assertEqual(second.composer.text(), "Keep my unsent draft")
        finally:
            second.prepare_close(); second.close_store(); second.close()

    def test_edit_regenerates_in_new_chat_and_keeps_original(self):
        self.view.composer.setText("Original request"); self.view.send(); self.pump()
        old = self.view.chat_id
        user = self.view.store.messages(old)[0]
        with patch.object(QInputDialog, "getMultiLineText", return_value=("Revised request", True)):
            self.view.branch_message(user, edit=True)
        self.pump()
        self.assertNotEqual(self.view.chat_id, old)
        self.assertEqual(self.view.store.messages(old)[0]["content"], "Original request")
        self.assertEqual(self.view.store.messages(self.view.chat_id)[0]["content"], "Revised request")

    def test_async_file_attachment_and_context(self):
        path = Path(self.tmp.name) / "evidence.txt"; path.write_text("MEASURED FACT: 12 N")
        self.view.attach_paths([str(path)]); self.pump()
        self.assertEqual(len(self.view.pending_attachments), 1)
        self.view.composer.setText("Summarise the evidence"); self.view.send(); self.pump()
        self.assertIn("MEASURED FACT: 12 N", json.dumps(FakeClient.requests[-1]))
        self.assertEqual(self.view.sources.count(), 1)

    def test_canvas_exports_real_pdf(self):
        path = Path(self.tmp.name) / "out.pdf"
        self.view.canvas.setPlainText("# Apollo Report\nMeasured result: 42.")
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(path), "")):
            self.view.save_canvas()
        self.assertTrue(path.read_bytes().startswith(b"%PDF"))
        self.assertIn("42", extract_attachment(path)["content"])

    def test_markdown_does_not_embed_raw_html_or_inline_remote_images(self):
        rendered = markdown_html("<script>do_bad_stuff()</script>\n![tracking](https://example.invalid/pixel.png)\n**Hello**")
        self.assertNotIn("<script", rendered)
        self.assertNotIn("<img", rendered)
        self.assertIn("Hello", rendered)

    def test_rendered_actions_copy_code_to_clipboard(self):
        ident = self.view.store.add_message(self.view.chat_id, "assistant", "```python\nprint(42)\n```")
        self.view.render()
        from PySide6.QtCore import QUrl
        self.view.anchor_clicked(QUrl(f"apollo://code/{ident}?token={self.view._action_token}"))
        self.assertEqual(QApplication.clipboard().text(), "print(42)")
        self.view.anchor_clicked(QUrl(f"apollo://copy/{ident}?token=wrong"))
        self.assertEqual(QApplication.clipboard().text(), "print(42)")

    def test_images_are_real_resized_snapshots(self):
        from PySide6.QtGui import QImage, QColor
        path = Path(self.tmp.name) / "photo.png"
        image = QImage(2000, 1000, QImage.Format_RGB32); image.fill(QColor("red")); image.save(str(path))
        data = extract_attachment(path)
        self.assertEqual(data["kind"], "image"); self.assertTrue(data["image"])
        self.assertIn("1600", data["notice"])

    def test_narrow_layout_uses_a_separate_canvas_window(self):
        self.view.resize(800, 700); self.app.processEvents()
        self.assertFalse(self.view.navigation.isVisible())
        self.view.show_inspector(0); self.app.processEvents()
        self.assertTrue(self.view.inspector_dialog.isVisible())
        self.assertTrue(self.view.inspector.isVisible())
        self.view.inspector_dialog.close()

    def test_legacy_chat_recall_is_not_available_to_scoped_tools(self):
        from apollo_chat_workspace import ScopedChatManager
        manager = ScopedChatManager(self.owner.module_manager)
        self.assertIsNone(manager.get_module("chat_memory_module"))
        with self.assertRaises(PermissionError):
            manager.execute("chat_memory_module", "previous_user_request", {})

    def test_regenerate_preserves_image_attachments(self):
        ident = self.view.store.add_attachment(attachment("image.png", "", "image", "IMAGE"), chat_id=self.view.chat_id)
        self.view.pending_attachments = [ident]
        self.view.composer.setText("Describe this image"); self.view.send(); self.pump()
        old = self.view.chat_id
        answer = self.view.store.messages(old)[-1]
        self.view.branch_message(answer); self.pump()
        self.assertNotEqual(self.view.chat_id, old)
        self.assertEqual(FakeClient.requests[-1][-1]["images"], ["IMAGE"])

    def test_vision_failure_is_saved_as_failed_not_as_an_answer(self):
        ident = self.view.store.add_attachment(attachment("image.png", "", "image", "IMAGE"), chat_id=self.view.chat_id)
        self.view.pending_attachments = [ident]
        self.view.composer.setText("Describe this image")
        with patch.object(FakeClient, "model_info", return_value={"capabilities": ["completion"]}):
            self.view.send(); self.pump()
        message = self.view.store.messages(self.view.chat_id)[-1]
        self.assertEqual(message["status"], "failed")
        self.assertIn("vision", message["content"])

    def test_unsent_attachment_is_restored_with_draft(self):
        path = Path(self.tmp.name) / "draft.txt"; path.write_text("Draft source")
        self.view.attach_paths([str(path)]); self.pump()
        self.view.composer.setText("My unsent question"); self.view.save_draft()
        second = ChatWorkspace(self.owner, self.tmp.name)
        try:
            self.assertEqual(second.composer.text(), "My unsent question")
            self.assertEqual(len(second.pending_attachments), 1)
            self.assertEqual(second.attachments_list.item(0).text(), "draft.txt")
        finally:
            second.prepare_close(); second.close_store(); second.close()


if __name__ == "__main__":
    unittest.main()
