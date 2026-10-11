"""Opt-in camera snapshots, image interpretation, and source-linked visual notes.

Only stored image IDs are accessible to chat tools. File picker import and webcam
access from the UI are explicitly user-triggered. No background camera stream.
"""
import base64
import hashlib
import ipaddress
import json
import os
import re
import socket
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MAX_IMAGE_BYTES = 8 * 1024 * 1024
DEFAULT_MODEL = "qwen2.5vl:3b"
IMAGE_ID = re.compile(r"^[a-f0-9]{20}\.(?:jpg|png|webp)$")
MODEL_NAME = re.compile(r"^[a-zA-Z0-9._:/-]{1,100}$")


def _kind(raw):
    if raw.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    raise ValueError("Only real JPEG, PNG and WebP images are supported.")


def _public_image_url(url):
    """Reject private networks and suspicious URL types before opening sockets."""
    value = str(url or "").strip()
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Paste a direct HTTPS image URL.")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Image URLs cannot include credentials or fragments.")
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise PermissionError("Local network hosts are not permitted.")
    if parsed.port not in (None, 443):
        raise PermissionError("Only the standard HTTPS port is permitted.")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        addresses = [
            ipaddress.ip_address(item[4][0])
            for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        ]
    if not addresses or any(
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
        or ip.is_reserved or ip.is_unspecified for ip in addresses
    ):
        raise PermissionError("Private or unsafe image hosts are blocked.")
    return value


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PermissionError("Image URL redirects are blocked. Use the final direct image URL.")


class Module:
    def __init__(self, context=None):
        self.context = context or {}
        self.base = Path(self.context.get("base_dir", ".")).resolve()
        self.folder = self.base / "storage" / "media" / "visual_learning"
        self.folder.mkdir(parents=True, exist_ok=True)
        self._analyses = {}
        self._lock = threading.RLock()

    def tools(self):
        return [
            {"name": "list_cameras", "description": "Probe connected USB cameras only when asked (may briefly activate their LEDs).",
             "parameters": {"type": "object", "properties": {}}},
            {"name": "capture_camera", "description": "Capture one webcam frame, never stream. Requires explicit camera permission for chat-tool access.",
             "parameters": {"type": "object", "properties": {"camera_index": {"type": "integer"}}}},
            {"name": "analyse_image", "description": "Ask a local Ollama vision model about an image already imported into Apollo visual storage.",
             "parameters": {"type": "object", "properties": {
                 "image_id": {"type": "string"}, "question": {"type": "string"}, "model": {"type": "string"}
             }, "required": ["image_id"]}},
            {"name": "fetch_online_image", "description": "Import a direct, public HTTPS image URL into local visual storage (never scrape private hosts).",
             "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
            {"name": "save_visual_note", "description": "Save an existing visual analysis as clearly labelled, unverified research memory.",
             "parameters": {"type": "object", "properties": {
                 "image_id": {"type": "string"}, "topic": {"type": "string"}
             }, "required": ["image_id", "topic"]}},
            {"name": "research_image", "description": "Search public web sources for a user-specified subject inferred from an analysed image and save research citations.",
             "parameters": {"type": "object", "properties": {
                 "image_id": {"type": "string"}, "topic": {"type": "string"}
             }, "required": ["image_id", "topic"]}},
        ]

    def _store(self, raw, source):
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("Image must be nonempty and under 8 MB.")
        extension = _kind(raw)
        digest = hashlib.sha256(raw).hexdigest()[:20]
        image_id = digest + "." + extension
        destination = self.folder / image_id
        if not destination.exists():
            destination.write_bytes(raw)
        metadata = {"image_id": image_id, "source": str(source)[:1000],
                    "imported_at": datetime.now(timezone.utc).isoformat()}
        (self.folder / (digest + ".json")).write_text(
            json.dumps(metadata, indent=2), encoding="utf-8")
        return {"image_id": image_id, "path": str(destination), "source": metadata["source"]}

    def _image_path(self, image_id):
        image_id = str(image_id or "")
        if not IMAGE_ID.fullmatch(image_id):
            raise ValueError("Use an Apollo image ID, not an arbitrary filesystem path.")
        target = (self.folder / image_id).resolve()
        if target.parent != self.folder.resolve() or not target.is_file():
            raise FileNotFoundError("Image not in Apollo visual storage.")
        if target.stat().st_size > MAX_IMAGE_BYTES:
            raise ValueError("Image exceeds the 8 MB size limit.")
        return target

    def _metadata(self, image_id):
        self._image_path(image_id)
        file = self.folder / (image_id.split(".")[0] + ".json")
        try:
            return json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"image_id": image_id, "source": "Local Apollo image"}

    def import_image(self, path):
        """Only invoked from a user's UI file selection, not an LLM tool."""
        file = Path(path).expanduser().resolve()
        if not file.is_file() or file.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("Choose a JPG, PNG or WebP image file.")
        if file.stat().st_size > MAX_IMAGE_BYTES:
            raise ValueError("Image exceeds 8 MB.")
        return self._store(file.read_bytes(), "file:" + str(file))

    def fetch_online_image(self, url):
        url = _public_image_url(url)
        request = urllib.request.Request(
            url, headers={"User-Agent": "ApolloVisualLearning/1.0", "Accept": "image/*"})
        opener = urllib.request.build_opener(_NoRedirect)
        with opener.open(request, timeout=15) as response:
            if not response.headers.get("Content-Type", "").lower().startswith("image/"):
                raise ValueError("URL does not serve an image.")
            raw = response.read(MAX_IMAGE_BYTES + 1)
        return self._store(raw, url)

    def list_cameras(self):
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("Install the optional camera package: pip install opencv-python") from exc
        devices = []
        for index in range(5):
            capture = cv2.VideoCapture(index, cv2.CAP_DSHOW) if sys.platform == "win32" else cv2.VideoCapture(index)
            try:
                if capture.isOpened():
                    devices.append({"index": index, "name": "Camera " + str(index)})
            finally:
                capture.release()
        return {"cameras": devices}

    def capture_camera(self, camera_index=0):
        """One short-lived snapshot; each call opens and releases the device."""
        index = int(camera_index)
        if not 0 <= index <= 8:
            raise ValueError("Camera index must be 0 to 8.")
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("Install the optional camera package: pip install opencv-python") from exc
        capture = cv2.VideoCapture(index, cv2.CAP_DSHOW) if sys.platform == "win32" else cv2.VideoCapture(index)
        try:
            if not capture.isOpened():
                raise RuntimeError("Cannot open camera. Check Windows camera privacy settings and other apps.")
            frame = None
            for _ in range(6):  # give auto-exposure time to settle
                ok, candidate = capture.read()
                if ok and candidate is not None:
                    frame = candidate
            if frame is None:
                raise RuntimeError("Camera opened but did not deliver a frame.")
            ok, encoded = cv2.imencode(".jpg", frame)
            if not ok:
                raise RuntimeError("Failed to encode camera frame.")
            return self._store(encoded.tobytes(), "camera:" + str(index))
        finally:
            capture.release()

    def analyse_image(self, image_id, question=None, model=None):
        path = self._image_path(image_id)
        raw = path.read_bytes()
        _kind(raw)  # reject renamed fake image files
        model = str(model or os.environ.get("APOLLO_VISION_MODEL") or DEFAULT_MODEL).strip()
        if not MODEL_NAME.fullmatch(model):
            raise ValueError("Invalid local vision model name.")
        prompt = str(question or "Describe this image accurately, including identifiable objects, text, diagrams, and uncertainties. Suggest useful topics to research.").strip()[:1500]
        payload = {"model": model, "stream": False, "messages": [
            {"role": "user", "content": (
                "You are analysing an image. Distinguish observed details from guesses. "
                "If text is illegible or an object is uncertain, say so. "
                "Never claim to have verified facts using web research. " + prompt),
             "images": [base64.b64encode(raw).decode("ascii")]}
        ]}
        request = urllib.request.Request(
            "http://127.0.0.1:11434/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.loads(response.read(256000).decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise RuntimeError("Vision model not installed. Run: ollama pull " + model) from exc
            raise RuntimeError("Local Ollama vision request failed: HTTP " + str(exc.code)) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError("Cannot reach Ollama at 127.0.0.1:11434, or vision analysis timed out.") from exc
        answer = str((data.get("message") or {}).get("content") or "").strip()
        if not answer:
            raise RuntimeError("The local vision model returned no description.")
        record = {"image_id": image_id, "model": model, "question": prompt,
                  "analysis": answer[:12000], "source": self._metadata(image_id).get("source", ""),
                  "analysed_at": datetime.now(timezone.utc).isoformat()}
        with self._lock:
            self._analyses[image_id] = record
        return dict(record)

    def save_visual_note(self, image_id, topic):
        topic = " ".join(str(topic or "").split())[:160]
        if not topic:
            raise ValueError("Name the subject so Apollo can find it in future chats.")
        self._image_path(image_id)
        with self._lock:
            analysis = dict(self._analyses.get(image_id) or {})
        if not analysis:
            raise ValueError("Analyse the image before saving a visual note.")
        note = "\n".join([
            "# Visual observation: " + topic, "",
            "Status: Unverified AI visual interpretation, not trained model weights.",
            "Source: " + analysis["source"], "Image ID: " + image_id,
            "Model: " + analysis["model"], "Observed at: " + analysis["analysed_at"],
            "", "## Question", analysis["question"], "",
            "## Visual analysis (may contain errors)", analysis["analysis"], "",
            "Always cross-check important claims against reliable primary sources.", "",
        ])
        research = self.base / "storage" / "training" / "research" / "visual"
        research.mkdir(parents=True, exist_ok=True)
        target = research / (image_id.split(".")[0] + ".md")
        target.write_text(note, encoding="utf-8")
        return {"saved": True, "path": str(target), "topic": topic,
                "note": "Searchable by Apollo's existing local Research & Training retrieval."}

    def research_image(self, image_id, topic):
        topic = " ".join(str(topic or "").split())[:160]
        if not topic:
            raise ValueError("Enter a subject to research; Apollo should not invent the search terms.")
        note = self.save_visual_note(image_id, topic)
        runtime = self.context.get("runtime")
        manager = getattr(runtime, "_manager", None)
        record = manager.get_module("training_module") if manager is not None else None
        if not record or not record.get("enabled") or record.get("instance") is None:
            raise RuntimeError("Enable Apollo's Research & Training module for web research.")
        filename = "visual/" + image_id.split(".")[0] + "_sources.md"
        result = manager.execute(
            "training_module", "explore_web_and_save",
            {"query": topic, "filename": filename, "limit": 5})
        return {"visual_note": note, "research": {
            "query": topic, "source_pages_fetched": result.get("source_pages_fetched", 0),
            "saved": result.get("saved", {})}}

    def run(self, action, arguments):
        data = arguments or {}
        if action == "list_cameras":
            return self.list_cameras()
        if action == "capture_camera":
            return self.capture_camera(data.get("camera_index", 0))
        if action == "analyse_image":
            return self.analyse_image(data.get("image_id"), data.get("question"), data.get("model"))
        if action == "fetch_online_image":
            return self.fetch_online_image(data.get("url"))
        if action == "save_visual_note":
            return self.save_visual_note(data.get("image_id"), data.get("topic"))
        if action == "research_image":
            return self.research_image(data.get("image_id"), data.get("topic"))
        raise KeyError(action)

    def self_test(self):
        assert _kind(b"\xff\xd8\xff\x00") == "jpg"
        assert _kind(b"\x89PNG\r\n\x1a\n") == "png"
        assert not IMAGE_ID.fullmatch("../secret.png")
        assert "capture_camera" in {tool["name"] for tool in self.tools()}
        return "Visual learning contracts passed (no camera or network accessed)."

    def build_ui(self, parent=None, ui_context=None):
        from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Qt
        from PySide6.QtGui import QPixmap
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
            QLineEdit, QComboBox, QPlainTextEdit, QFileDialog, QMessageBox
        )

        class Signals(QObject):
            finished = Signal(object)
            failed = Signal(str)

        class Job(QRunnable):
            def __init__(self, work):
                super().__init__()
                self.work = work
                self.signals = Signals()

            def run(self):
                try:
                    self.signals.finished.emit(self.work())
                except Exception as exc:
                    self.signals.failed.emit(str(exc))

        page = QWidget(parent)
        root = QVBoxLayout(page)
        title = QLabel("Apollo Vision Lab")
        title.setStyleSheet("font-size:22px;font-weight:700;")
        root.addWidget(title)
        description = QLabel(
            "Capture one webcam image, import a file or paste a direct HTTPS image URL. "
            "Visual understanding runs through local Ollama. Nothing is remembered or "
            "researched online until you choose those actions.")
        description.setWordWrap(True)
        root.addWidget(description)

        cameras = QComboBox()
        cameras.addItem("Camera 0", 0)
        for i in range(1, 5):
            cameras.addItem("Camera " + str(i), i)
        detect = QPushButton("Detect cameras")
        capture = QPushButton("Capture photo")
        add_file = QPushButton("Open image file")
        row = QHBoxLayout()
        for widget in (cameras, detect, capture, add_file):
            row.addWidget(widget)
        root.addLayout(row)

        image_url = QLineEdit()
        image_url.setPlaceholderText("Direct public HTTPS image URL")
        download = QPushButton("Load web image")
        row2 = QHBoxLayout()
        row2.addWidget(image_url, 1)
        row2.addWidget(download)
        root.addLayout(row2)

        preview = QLabel("No image selected")
        preview.setAlignment(Qt.AlignCenter)
        preview.setMinimumHeight(170)
        preview.setMaximumHeight(260)
        root.addWidget(preview)
        model = QLineEdit(os.environ.get("APOLLO_VISION_MODEL") or DEFAULT_MODEL)
        question = QLineEdit()
        question.setPlaceholderText("What should Apollo look for in this image?")
        topic = QLineEdit()
        topic.setPlaceholderText("Topic for saved memory / web research (e.g. Arduino UNO)")
        root.addWidget(QLabel("Vision model (Ollama)"))
        root.addWidget(model)
        root.addWidget(question)
        root.addWidget(topic)

        analyse = QPushButton("Analyse image")
        remember = QPushButton("Save to memory")
        research = QPushButton("Research topic online + save sources")
        row3 = QHBoxLayout()
        for widget in (analyse, remember, research):
            row3.addWidget(widget)
        root.addLayout(row3)
        output = QPlainTextEdit()
        output.setReadOnly(True)
        root.addWidget(output, 1)
        selected = {"id": ""}
        jobs = []
        pool = QThreadPool.globalInstance()

        def error(message):
            output.setPlainText("Vision Lab error: " + str(message))
            QMessageBox.warning(page, "Apollo Vision Lab", str(message))

        def submit(work, done):
            task = Job(work)
            jobs.append(task)
            task.signals.finished.connect(done)
            task.signals.failed.connect(error)
            task.signals.finished.connect(lambda _value, t=task: jobs.remove(t) if t in jobs else None)
            task.signals.failed.connect(lambda _value, t=task: jobs.remove(t) if t in jobs else None)
            pool.start(task)

        def selected_image(result):
            selected["id"] = result["image_id"]
            pixmap = QPixmap(result["path"])
            preview.setPixmap(pixmap.scaled(480, 250, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            output.setPlainText("Ready: " + result["image_id"] + "\nSource: " + result["source"])

        def open_file():
            filename, _ = QFileDialog.getOpenFileName(
                page, "Open image", "", "Images (*.png *.jpg *.jpeg *.webp)")
            if filename:
                try:
                    selected_image(self.import_image(filename))
                except Exception as exc:
                    error(exc)

        def capture_clicked():
            output.setPlainText("Capturing one camera frame...")
            index = cameras.currentData()
            submit(lambda: self.capture_camera(index), selected_image)

        def detect_clicked():
            output.setPlainText("Checking connected camera indices...")
            def done(result):
                cameras.clear()
                for item in result["cameras"]:
                    cameras.addItem(item["name"], item["index"])
                if not result["cameras"]:
                    output.setPlainText("No camera detected. Check connection and camera permissions.")
                else:
                    output.setPlainText("Detected " + str(len(result["cameras"])) + " camera(s).")
            submit(self.list_cameras, done)

        def download_clicked():
            url = image_url.text().strip()
            if url:
                submit(lambda: self.fetch_online_image(url), selected_image)

        def analyse_clicked():
            if not selected["id"]:
                error("Choose or capture an image first.")
                return
            image_id = selected["id"]
            output.setPlainText("Asking local vision model to analyse the image...")
            prompt = question.text()
            model_name = model.text()
            submit(lambda: self.analyse_image(image_id, prompt, model_name),
                   lambda result: output.setPlainText(result["analysis"]))

        def remember_clicked():
            if not selected["id"] or not topic.text().strip():
                error("Analyse an image and enter a topic before saving memory.")
                return
            image_id = selected["id"]
            subject = topic.text().strip()
            submit(lambda: self.save_visual_note(image_id, subject),
                   lambda result: output.setPlainText("Visual memory saved:\n" + result["path"]))

        def research_clicked():
            if not selected["id"] or not topic.text().strip():
                error("Analyse an image and enter a research topic first.")
                return
            output.setPlainText("Searching public sources for: " + topic.text())
            image_id = selected["id"]
            subject = topic.text().strip()
            submit(lambda: self.research_image(image_id, subject),
                   lambda result: output.setPlainText(json.dumps(result, indent=2)))

        detect.clicked.connect(detect_clicked)
        capture.clicked.connect(capture_clicked)
        add_file.clicked.connect(open_file)
        download.clicked.connect(download_clicked)
        analyse.clicked.connect(analyse_clicked)
        remember.clicked.connect(remember_clicked)
        research.clicked.connect(research_clicked)
        return page
