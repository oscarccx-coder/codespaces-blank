import subprocess
import sys


def _hidden_subprocess_kwargs():
    if sys.platform != "win32":
        return {}

    kwargs = {}

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if creationflags:
        kwargs["creationflags"] = creationflags

    startupinfo_cls = getattr(subprocess, "STARTUPINFO", None)
    startf_use_showwindow = getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
    sw_hide = getattr(subprocess, "SW_HIDE", 0)

    if startupinfo_cls is not None:
        startupinfo = startupinfo_cls()
        startupinfo.dwFlags |= startf_use_showwindow
        startupinfo.wShowWindow = sw_hide
        kwargs["startupinfo"] = startupinfo

    return kwargs


class Module:
    def __init__(self, context=None):
        self.context = context or {}

    def tools(self):
        return [
            {
                "name": "gpu_status",
                "description": (
                    "Read NVIDIA GPU name, utilization, VRAM, temperature and power "
                    "using nvidia-smi."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "gpu_processes",
                "description": (
                    "List NVIDIA compute processes and their reported GPU memory usage."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        ]

    def _run(self, args):
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=5,
                **_hidden_subprocess_kwargs(),
            )
        except FileNotFoundError:
            raise RuntimeError(
                "nvidia-smi was not found. Install/update the NVIDIA driver."
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("nvidia-smi timed out.")

        if proc.returncode != 0:
            message = (proc.stderr or proc.stdout or "nvidia-smi failed").strip()
            raise RuntimeError(message)

        return proc.stdout.strip()

    def _status(self):
        output = self._run([
            "nvidia-smi",
            "--query-gpu="
            "name,utilization.gpu,memory.used,memory.total,"
            "temperature.gpu,power.draw,power.limit,driver_version",
            "--format=csv,noheader,nounits",
        ])

        gpus = []

        for index, line in enumerate(output.splitlines()):
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 8:
                continue

            def number(value):
                try:
                    return float(value)
                except Exception:
                    return None

            gpus.append({
                "index": index,
                "name": parts[0],
                "utilization_percent": number(parts[1]),
                "memory_used_mb": number(parts[2]),
                "memory_total_mb": number(parts[3]),
                "temperature_c": number(parts[4]),
                "power_draw_w": number(parts[5]),
                "power_limit_w": number(parts[6]),
                "driver_version": parts[7],
            })

        return {
            "available": bool(gpus),
            "gpu_count": len(gpus),
            "gpus": gpus,
        }

    def _processes(self):
        try:
            output = self._run([
                "nvidia-smi",
                "--query-compute-apps=pid,process_name,used_gpu_memory",
                "--format=csv,noheader,nounits",
            ])
        except RuntimeError as exc:
            # Some systems return a nonzero status when there are no compute apps.
            text = str(exc).lower()
            if "no running processes" in text or "not supported" in text:
                return {"processes": []}
            raise

        rows = []
        for line in output.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 3:
                continue
            try:
                pid = int(parts[0])
            except Exception:
                pid = None
            try:
                memory = float(parts[2])
            except Exception:
                memory = None

            rows.append({
                "pid": pid,
                "process_name": parts[1],
                "memory_mb": memory,
            })

        return {"processes": rows}

    def self_test(self):
        # Do not require an NVIDIA GPU in validation environments.
        assert "gpu_status" in {x["name"] for x in self.tools()}
        assert "gpu_processes" in {x["name"] for x in self.tools()}
        return "GPU monitor API self-test passed."

    def build_ui(self, parent=None, ui_context=None):
        """
        Optional Apollo module UI.

        Imported lazily so headless module validation does not require Qt widgets.
        """
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
            QProgressBar, QFrame, QTextBrowser
        )

        page = QWidget(parent)
        layout = QVBoxLayout(page)

        title = QLabel("GPU Monitor")
        title.setStyleSheet(
            "font-size:22px;font-weight:700;color:#e7fffb;"
        )
        layout.addWidget(title)

        subtitle = QLabel(
            "Live NVIDIA GPU load, VRAM, temperature and power from nvidia-smi."
        )
        subtitle.setStyleSheet("color:#91bdb6;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        card = QFrame()
        card.setStyleSheet(
            "QFrame {"
            "background:#102522;"
            "border:1px solid #21443e;"
            "border-radius:12px;"
            "padding:10px;"
            "}"
        )
        card_layout = QVBoxLayout(card)

        name_label = QLabel("GPU: checking...")
        name_label.setStyleSheet(
            "font-size:16px;font-weight:700;color:#dffbf5;"
        )

        usage_label = QLabel("Usage: —")
        vram_label = QLabel("VRAM: —")
        temp_label = QLabel("Temperature: —")
        power_label = QLabel("Power: —")

        for widget in (usage_label, vram_label, temp_label, power_label):
            widget.setStyleSheet("color:#b9d9d3;")

        usage_bar = QProgressBar()
        usage_bar.setRange(0, 100)

        vram_bar = QProgressBar()
        vram_bar.setRange(0, 100)

        refresh_btn = QPushButton("Refresh GPU")

        process_box = QTextBrowser()
        process_box.setPlaceholderText(
            "GPU compute processes will appear here."
        )
        process_box.setMaximumHeight(180)

        card_layout.addWidget(name_label)
        card_layout.addWidget(usage_label)
        card_layout.addWidget(usage_bar)
        card_layout.addWidget(vram_label)
        card_layout.addWidget(vram_bar)
        card_layout.addWidget(temp_label)
        card_layout.addWidget(power_label)
        card_layout.addWidget(refresh_btn)
        card_layout.addWidget(process_box)

        layout.addWidget(card)
        layout.addStretch()

        def refresh():
            try:
                status = self._status()
                if not status["gpus"]:
                    name_label.setText("GPU: no NVIDIA GPU detected")
                    return

                gpu = status["gpus"][0]

                usage = int(gpu.get("utilization_percent") or 0)
                used = float(gpu.get("memory_used_mb") or 0)
                total = float(gpu.get("memory_total_mb") or 0)
                vram_percent = int((used / total) * 100) if total else 0

                name_label.setText(
                    f"GPU: {gpu.get('name', 'NVIDIA GPU')}"
                )
                usage_label.setText(f"Usage: {usage}%")
                usage_bar.setValue(max(0, min(usage, 100)))

                vram_label.setText(
                    f"VRAM: {used/1024:.2f} / {total/1024:.2f} GB"
                )
                vram_bar.setValue(max(0, min(vram_percent, 100)))

                temp = gpu.get("temperature_c")
                power = gpu.get("power_draw_w")
                limit = gpu.get("power_limit_w")

                temp_label.setText(
                    f"Temperature: {temp:.0f}°C"
                    if temp is not None else "Temperature: —"
                )

                if power is not None and limit is not None:
                    power_label.setText(
                        f"Power: {power:.1f} / {limit:.1f} W"
                    )
                elif power is not None:
                    power_label.setText(f"Power: {power:.1f} W")
                else:
                    power_label.setText("Power: —")

                try:
                    processes = self._processes()["processes"]
                    if processes:
                        lines = []
                        for process in processes:
                            lines.append(
                                f"PID {process.get('pid')} | "
                                f"{process.get('process_name')} | "
                                f"{process.get('memory_mb')} MB"
                            )
                        process_box.setPlainText("\n".join(lines))
                    else:
                        process_box.setPlainText(
                            "No NVIDIA compute processes reported."
                        )
                except Exception as exc:
                    process_box.setPlainText(
                        f"Process query unavailable: {exc}"
                    )

            except Exception as exc:
                name_label.setText("GPU Monitor unavailable")
                process_box.setPlainText(str(exc))

        refresh_btn.clicked.connect(refresh)

        timer = QTimer(page)
        timer.setInterval(2000)
        timer.timeout.connect(refresh)
        timer.start()

        refresh()
        return page

    def run(self, action, arguments):
        if action == "gpu_status":
            return self._status()
        if action == "gpu_processes":
            return self._processes()
        raise KeyError(action)
