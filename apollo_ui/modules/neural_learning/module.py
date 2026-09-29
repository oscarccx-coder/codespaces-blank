import json
import math
import random
import re
import threading
import time
from collections import Counter
from pathlib import Path


TOKEN_RE = re.compile(r"[a-zA-Z0-9']+")


def tokenize(text):
    return TOKEN_RE.findall((text or "").lower())


def feature_tokens(text):
    words = tokenize(text)
    features = list(words)
    features.extend(
        "__bg__" + words[i] + "_" + words[i + 1]
        for i in range(len(words) - 1)
    )
    return features


def softmax(values):
    if not values:
        return []
    maximum = max(values)
    exps = [math.exp(max(-60.0, min(60.0, x - maximum))) for x in values]
    total = sum(exps) or 1.0
    return [x / total for x in exps]


class Module:
    """Apollo's small, persistent, user-trainable text classifier."""

    MIN_EXAMPLES_PER_LABEL = 3

    def __init__(self, context=None):
        context = context or {}
        self.validation = bool(context.get("validation", False))
        self.base_dir = Path(context.get("base_dir", ".")).resolve()

        if self.validation:
            self.state_path = None
        else:
            storage = self.base_dir / "storage"
            storage.mkdir(parents=True, exist_ok=True)
            self.state_path = storage / "state" / "neural_learning_state.json"

        self._lock = threading.RLock()
        self.examples = []
        self.vocab = []
        self.labels = []
        self.hidden_size = 24
        self.w1 = []
        self.b1 = []
        self.w2 = []
        self.b2 = []
        self.trained = False
        self.ready_for_use = False
        self.last_training = {}
        self.training_status = {
            "active": False,
            "percent": 0,
            "phase": "idle",
            "restart": 0,
            "restarts": 0,
            "epoch": 0,
            "max_epochs": 0,
        }
        self._load()

    def tools(self):
        return [
            {
                "name": "add_training_example",
                "description": (
                    "Teach Apollo's auxiliary neural classifier a labelled text example. "
                    "Use several different examples for every label before training."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "label": {"type": "string"}
                    },
                    "required": ["text", "label"]
                }
            },
            {
                "name": "train_network",
                "description": (
                    "Train and validate Apollo's small neural classifier. Training uses "
                    "multiple restarts and a held-out validation set; a model is only "
                    "marked ready_for_use when it clears the quality gate."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "epochs": {"type": "integer"},
                        "learning_rate": {"type": "number"},
                        "hidden_size": {"type": "integer"},
                        "restarts": {"type": "integer"}
                    }
                }
            },
            {
                "name": "predict_label",
                "description": "Predict learned labels for text using the trained network.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "top_k": {"type": "integer"}
                    },
                    "required": ["text"]
                }
            },
            {
                "name": "neural_status",
                "description": "Show dataset quality, training progress and model evaluation.",
                "parameters": {"type": "object", "properties": {}}
            },
            {
                "name": "list_training_examples",
                "description": "List recent labelled examples.",
                "parameters": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer"}}
                }
            }
        ]

    def _load(self):
        if self.state_path is None or not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return
        with self._lock:
            self.examples = list(data.get("examples", []))
            self.vocab = list(data.get("vocab", []))
            self.labels = list(data.get("labels", []))
            self.hidden_size = int(data.get("hidden_size", 24))
            self.w1 = list(data.get("w1", []))
            self.b1 = list(data.get("b1", []))
            self.w2 = list(data.get("w2", []))
            self.b2 = list(data.get("b2", []))
            self.trained = bool(data.get("trained", False))
            self.ready_for_use = bool(data.get("ready_for_use", self.trained))
            self.last_training = dict(data.get("last_training", {}))

    def _save(self):
        if self.state_path is None:
            return
        with self._lock:
            data = {
                "version": 2,
                "examples": self.examples,
                "vocab": self.vocab,
                "labels": self.labels,
                "hidden_size": self.hidden_size,
                "w1": self.w1,
                "b1": self.b1,
                "w2": self.w2,
                "b2": self.b2,
                "trained": self.trained,
                "ready_for_use": self.ready_for_use,
                "last_training": self.last_training,
            }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        temp.replace(self.state_path)

    def _class_counts(self):
        counts = Counter(str(x.get("label", "")).lower() for x in self.examples)
        counts.pop("", None)
        return dict(sorted(counts.items()))

    def _add_example(self, text, label):
        text = str(text or "").strip()
        label = str(label or "").strip().lower()
        if not text:
            raise ValueError("text cannot be empty.")
        if not label:
            raise ValueError("label cannot be empty.")
        if len(text) > 4000:
            raise ValueError("Training example is too long.")
        if len(label) > 80:
            raise ValueError("Label is too long.")

        normalized = " ".join(tokenize(text))
        with self._lock:
            for item in self.examples:
                if (
                    " ".join(tokenize(item.get("text", ""))) == normalized
                    and str(item.get("label", "")).lower() == label
                ):
                    return {
                        "added": False,
                        "duplicate": True,
                        "example_count": len(self.examples),
                        "label": label,
                        "class_counts": self._class_counts(),
                    }
            self.examples.append({"text": text, "label": label})
            self.trained = False
            self.ready_for_use = False
            count = len(self.examples)
            counts = self._class_counts()
        self._save()
        return {
            "added": True,
            "duplicate": False,
            "example_count": count,
            "label": label,
            "class_counts": counts,
        }

    @staticmethod
    def _make_vocab_from(examples):
        counts = Counter()
        for item in examples:
            counts.update(feature_tokens(item["text"]))
        return [word for word, _ in counts.most_common(2500)]

    def _vector(self, text):
        counts = Counter(feature_tokens(text))
        maximum = max(counts.values(), default=1)
        return [counts.get(word, 0) / maximum for word in self.vocab]

    @staticmethod
    def _dot(weights, values, bias):
        return bias + sum(w * x for w, x in zip(weights, values))

    def _forward(self, x, w1=None, b1=None, w2=None, b2=None):
        w1 = self.w1 if w1 is None else w1
        b1 = self.b1 if b1 is None else b1
        w2 = self.w2 if w2 is None else w2
        b2 = self.b2 if b2 is None else b2
        hidden = [
            math.tanh(self._dot(w1[h], x, b1[h]))
            for h in range(len(w1))
        ]
        logits = [self._dot(w2[o], hidden, b2[o]) for o in range(len(w2))]
        return hidden, softmax(logits)

    def _dataset_score(self, dataset):
        if not dataset:
            return 0.0, 0.0
        label_index = {label: i for i, label in enumerate(self.labels)}
        correct = 0
        loss = 0.0
        for item in dataset:
            x = self._vector(item["text"])
            _, probs = self._forward(x)
            target = label_index[item["label"]]
            predicted = max(range(len(probs)), key=lambda i: probs[i])
            if predicted == target:
                correct += 1
            loss += -math.log(max(probs[target], 1e-12))
        return correct / len(dataset), loss / len(dataset)

    def _stratified_split(self, seed=2026):
        rng = random.Random(seed)
        grouped = {}
        for item in self.examples:
            grouped.setdefault(item["label"], []).append(dict(item))

        too_small = {
            label: len(items)
            for label, items in grouped.items()
            if len(items) < self.MIN_EXAMPLES_PER_LABEL
        }
        if too_small:
            detail = ", ".join(f"{k}={v}" for k, v in sorted(too_small.items()))
            raise ValueError(
                f"Need at least {self.MIN_EXAMPLES_PER_LABEL} different examples per label "
                f"before training. Currently: {detail}."
            )
        if len(grouped) < 2:
            raise ValueError("Neural training needs at least two different labels.")

        train, validation = [], []
        for label, items in sorted(grouped.items()):
            rng.shuffle(items)
            holdout = max(1, round(len(items) * 0.25))
            holdout = min(holdout, len(items) - 2)
            validation.extend(items[:holdout])
            train.extend(items[holdout:])
        rng.shuffle(train)
        rng.shuffle(validation)
        return train, validation

    @staticmethod
    def _copy_model(w1, b1, w2, b2):
        return (
            [row[:] for row in w1],
            list(b1),
            [row[:] for row in w2],
            list(b2),
        )

    def _set_progress(self, **updates):
        with self._lock:
            self.training_status.update(updates)

    def _train(self, epochs=1000, learning_rate=0.07, hidden_size=32, restarts=4):
        start_time = time.perf_counter()
        epochs = max(100, min(int(epochs), 3000))
        learning_rate = max(0.002, min(float(learning_rate), 0.30))
        hidden_size = max(8, min(int(hidden_size), 96))
        restarts = max(1, min(int(restarts), 8))

        with self._lock:
            train_examples, validation_examples = self._stratified_split()
            self.vocab = self._make_vocab_from(train_examples)
            self.labels = sorted({item["label"] for item in self.examples})
            self.hidden_size = hidden_size
            all_examples = [dict(x) for x in self.examples]

        if not self.vocab:
            raise ValueError("Training examples contain no usable words.")

        label_index = {label: i for i, label in enumerate(self.labels)}
        train_data = [(self._vector(x["text"]), label_index[x["label"]]) for x in train_examples]
        input_size = len(self.vocab)
        output_size = len(self.labels)
        best_global = None

        self._set_progress(
            active=True,
            percent=0,
            phase="training",
            restart=0,
            restarts=restarts,
            epoch=0,
            max_epochs=epochs,
        )

        try:
            for restart in range(restarts):
                rng = random.Random(1337 + restart * 7919)
                scale1 = 1.0 / math.sqrt(max(1, input_size))
                scale2 = 1.0 / math.sqrt(max(1, hidden_size))
                w1 = [[rng.uniform(-scale1, scale1) for _ in range(input_size)] for _ in range(hidden_size)]
                b1 = [0.0 for _ in range(hidden_size)]
                w2 = [[rng.uniform(-scale2, scale2) for _ in range(hidden_size)] for _ in range(output_size)]
                b2 = [0.0 for _ in range(output_size)]

                self.w1, self.b1, self.w2, self.b2 = w1, b1, w2, b2
                best_restart = None
                no_improvement = 0
                patience_checks = 18
                check_every = 10

                for epoch in range(1, epochs + 1):
                    order = list(range(len(train_data)))
                    rng.shuffle(order)
                    epoch_loss = 0.0

                    for position in order:
                        x, target = train_data[position]
                        hidden, probs = self._forward(x)
                        epoch_loss += -math.log(max(probs[target], 1e-12))
                        delta2 = list(probs)
                        delta2[target] -= 1.0
                        delta1 = []
                        for h in range(hidden_size):
                            back = sum(w2[o][h] * delta2[o] for o in range(output_size))
                            delta1.append(back * (1.0 - hidden[h] * hidden[h]))

                        for o in range(output_size):
                            for h in range(hidden_size):
                                w2[o][h] -= learning_rate * delta2[o] * hidden[h]
                            b2[o] -= learning_rate * delta2[o]

                        for h in range(hidden_size):
                            for i, value in enumerate(x):
                                if value:
                                    w1[h][i] -= learning_rate * delta1[h] * value
                            b1[h] -= learning_rate * delta1[h]

                    if epoch % check_every == 0 or epoch == epochs:
                        self.w1, self.b1, self.w2, self.b2 = w1, b1, w2, b2
                        val_accuracy, val_loss = self._dataset_score(validation_examples)
                        train_accuracy, _ = self._dataset_score(train_examples)
                        metric = (val_accuracy, -val_loss, train_accuracy)
                        if best_restart is None or metric > best_restart[0]:
                            best_restart = (
                                metric,
                                self._copy_model(w1, b1, w2, b2),
                                epoch,
                                val_accuracy,
                                val_loss,
                                train_accuracy,
                                epoch_loss / max(1, len(train_data)),
                            )
                            no_improvement = 0
                        else:
                            no_improvement += 1

                        overall = ((restart * epochs) + epoch) / (restarts * epochs)
                        self._set_progress(
                            active=True,
                            percent=min(99, int(overall * 100)),
                            phase="training",
                            restart=restart + 1,
                            epoch=epoch,
                        )
                        if no_improvement >= patience_checks:
                            break

                if best_restart is not None:
                    if best_global is None or best_restart[0] > best_global[0]:
                        best_global = best_restart

            if best_global is None:
                raise RuntimeError("Training failed to produce a model.")

            _, model, best_epoch, val_accuracy, val_loss, train_accuracy, train_loss = best_global
            self.w1, self.b1, self.w2, self.b2 = model
            self.trained = True
            # Quality gate: do not influence normal Apollo chat unless the held-out
            # examples show the network learned something beyond random guessing.
            random_baseline = 1.0 / max(2, len(self.labels))
            threshold = min(0.75, random_baseline + 0.20)
            self.ready_for_use = bool(val_accuracy >= threshold)

            duration = time.perf_counter() - start_time
            self.last_training = {
                "requested_epochs": epochs,
                "best_epoch": best_epoch,
                "restarts": restarts,
                "learning_rate": learning_rate,
                "hidden_size": hidden_size,
                "vocab_size": len(self.vocab),
                "labels": list(self.labels),
                "example_count": len(all_examples),
                "train_count": len(train_examples),
                "validation_count": len(validation_examples),
                "training_accuracy": round(train_accuracy, 4),
                "validation_accuracy": round(val_accuracy, 4),
                "validation_loss": round(val_loss, 6),
                "training_loss": round(train_loss, 6),
                "quality_threshold": round(threshold, 4),
                "ready_for_use": self.ready_for_use,
                "duration_seconds": round(duration, 3),
                "class_counts": self._class_counts(),
            }
            self._save()
            self._set_progress(active=False, percent=100, phase="complete")
            return {"trained": True, **self.last_training}
        except Exception:
            self._set_progress(active=False, phase="failed")
            raise

    def _predict(self, text, top_k=3):
        if not self.trained:
            raise RuntimeError("Neural network has not been trained since the latest examples were added.")
        if not self.vocab or not self.labels:
            raise RuntimeError("Neural network model state is incomplete.")
        text = str(text or "").strip()
        if not text:
            raise ValueError("text cannot be empty.")
        try:
            top_k = int(top_k)
        except (TypeError, ValueError):
            top_k = 3
        top_k = max(1, min(top_k, len(self.labels)))
        x = self._vector(text)
        _, probs = self._forward(x)
        ranked = sorted(zip(self.labels, probs), key=lambda p: p[1], reverse=True)[:top_k]
        return {
            "text": text,
            "predictions": [
                {"label": label, "confidence": round(prob, 4)}
                for label, prob in ranked
            ],
            "known_feature_count": sum(1 for value in x if value),
            "ready_for_use": self.ready_for_use,
            "backend": "pure_python_mlp_v2",
        }

    def _status(self):
        with self._lock:
            counts = self._class_counts()
            progress = dict(self.training_status)
            last = dict(self.last_training)
            return {
                "trained": self.trained,
                "ready_for_use": self.ready_for_use,
                "example_count": len(self.examples),
                "class_counts": counts,
                "minimum_examples_per_label": self.MIN_EXAMPLES_PER_LABEL,
                "known_labels": sorted(counts),
                "vocab_size": len(self.vocab),
                "hidden_size": self.hidden_size if self.trained else None,
                "backend": "pure_python_mlp_v2",
                "last_training": last,
                "training": progress,
                "storage": "in-memory validation state" if self.state_path is None else str(self.state_path),
            }

    def self_test(self):
        with self._lock:
            self.examples = []
            self.trained = False
            self.ready_for_use = False
        samples = [
            ("hello good morning friend", "greeting"),
            ("hi there nice to see you", "greeting"),
            ("good evening hello apollo", "greeting"),
            ("write python code for a file", "coding"),
            ("build a python module", "coding"),
            ("debug this program script", "coding"),
        ]
        for text, label in samples:
            self._add_example(text, label)
        result = self._train(epochs=500, learning_rate=0.08, hidden_size=16, restarts=2)
        assert result["trained"] is True
        p1 = self._predict("hello good morning", 1)
        p2 = self._predict("write python program", 1)
        assert p1["predictions"][0]["label"] == "greeting"
        assert p2["predictions"][0]["label"] == "coding"
        return "Neural MLP v2 train/validation/predict tests passed."

    def build_ui(self, parent=None, ui_context=None):
        from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
            QPushButton, QMessageBox, QTextBrowser, QProgressBar
        )

        module = self

        class Signals(QObject):
            finished = Signal(object)
            failed = Signal(str)
            completed = Signal()

        class TrainTask(QRunnable):
            def __init__(self):
                super().__init__()
                self.signals = Signals()
                self.setAutoDelete(True)

            @Slot()
            def run(self):
                try:
                    self.signals.finished.emit(module._train(1000, 0.07, 32, 4))
                except Exception as exc:
                    self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
                finally:
                    self.signals.completed.emit()

        page = QWidget(parent)
        layout = QVBoxLayout(page)
        title = QLabel("Neural Learning")
        title.setStyleSheet("font-size:22px;font-weight:700;color:#e7fffb;")
        info = QLabel(
            "Use at least 3 different examples for every label. Training now uses a "
            "held-out validation set and multiple restarts, so Apollo only trusts a "
            "network that proves it learned the pattern."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#91bdb6;")
        text_input = QLineEdit()
        text_input.setPlaceholderText("Training example")
        label_input = QLineEdit()
        label_input.setPlaceholderText("Label, e.g. coding")
        controls = QHBoxLayout()
        add_btn = QPushButton("Add Example")
        train_btn = QPushButton("Train + Validate")
        predict_btn = QPushButton("Predict")
        controls.addWidget(add_btn)
        controls.addWidget(train_btn)
        controls.addWidget(predict_btn)
        controls.addStretch()
        progress = QProgressBar()
        progress.setRange(0, 100)
        output = QTextBrowser()
        layout.addWidget(title)
        layout.addWidget(info)
        layout.addWidget(text_input)
        layout.addWidget(label_input)
        layout.addLayout(controls)
        layout.addWidget(progress)
        layout.addWidget(output, 1)
        pool = QThreadPool.globalInstance()
        active = {"task": None}

        def show_status():
            status = module._status()
            training = status.get("training", {})
            progress.setValue(int(training.get("percent", 0)))
            last = status.get("last_training", {})
            output.setPlainText(
                f"Examples: {status.get('example_count')}\n"
                f"Per label: {status.get('class_counts')}\n"
                f"Trained: {status.get('trained')}\n"
                f"Ready for Apollo chat: {status.get('ready_for_use')}\n"
                f"Validation accuracy: {last.get('validation_accuracy', 'n/a')}\n"
                f"Training duration: {last.get('duration_seconds', 'n/a')} s\n"
                f"Training phase: {training.get('phase', 'idle')} "
                f"{training.get('percent', 0)}%"
            )

        def add_example():
            try:
                result = module._add_example(text_input.text(), label_input.text())
                text_input.clear()
                label_input.clear()
                show_status()
                if result.get("duplicate"):
                    QMessageBox.information(page, "Neural Learning", "That exact labelled example already exists.")
            except Exception as exc:
                QMessageBox.warning(page, "Neural Learning", str(exc))

        def train():
            if active["task"] is not None:
                return
            train_btn.setEnabled(False)
            task = TrainTask()
            active["task"] = task
            task.signals.finished.connect(lambda result: show_status())
            task.signals.failed.connect(lambda err: QMessageBox.warning(page, "Neural Learning", err))
            def complete():
                active["task"] = None
                train_btn.setEnabled(True)
                show_status()
            task.signals.completed.connect(complete)
            pool.start(task)

        def predict():
            try:
                result = module._predict(text_input.text(), 3)
                output.setPlainText(
                    "\n".join(
                        f"{x['label']}: {round(x['confidence'] * 100, 1)}%"
                        for x in result.get("predictions", [])
                    )
                )
            except Exception as exc:
                QMessageBox.warning(page, "Neural Learning", str(exc))

        timer = QTimer(page)
        timer.setInterval(250)
        timer.timeout.connect(show_status)
        timer.start()
        add_btn.clicked.connect(add_example)
        train_btn.clicked.connect(train)
        predict_btn.clicked.connect(predict)
        show_status()
        return page

    def run(self, action, arguments):
        arguments = arguments or {}
        if action == "add_training_example":
            return self._add_example(arguments.get("text"), arguments.get("label"))
        if action == "train_network":
            return self._train(
                arguments.get("epochs", 1000),
                arguments.get("learning_rate", 0.07),
                arguments.get("hidden_size", 32),
                arguments.get("restarts", 4),
            )
        if action == "predict_label":
            return self._predict(arguments.get("text"), arguments.get("top_k", 3))
        if action == "neural_status":
            return self._status()
        if action == "list_training_examples":
            try:
                limit = int(arguments.get("limit", 20))
            except (TypeError, ValueError):
                limit = 20
            limit = max(1, min(limit, 100))
            with self._lock:
                return list(self.examples[-limit:])
        raise KeyError(f"Unknown action: {action}")
