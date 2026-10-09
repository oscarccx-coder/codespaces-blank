from pathlib import Path

root = Path(__file__).resolve().parents[1]
main = (root / "main.py").read_text(encoding="utf-8")
voice = (root / "modules" / "voice_imprint_trainer" / "module.py").read_text(encoding="utf-8")

assert "def _stabilize_module_ui_controls(self, widget):" in main
assert "def _wrap_module_ui_for_host(self, widget):" in main
assert "field.setMinimumHeight(max(field.minimumHeight(), 38))" in main
assert "text_widget.setMinimumHeight(max(text_widget.minimumHeight(), 96))" in main
assert "host.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)" in main
assert "self.apps_list.setMaximumHeight(130)" in main
assert "self.apps_host.setMinimumHeight(460)" in main
assert "QPlainTextEdit" in main
assert "QAbstractSpinBox" in main

assert "profile_name.setMinimumHeight(38)" in voice
assert "source_path.setMinimumHeight(38)" in voice
assert "model_dir.setMinimumHeight(38)" in voice
assert "language.setMinimumHeight(38)" in voice
assert "test_text.setMinimumHeight(96)" in voice
assert "output.setMinimumHeight(170)" in voice

print("UI form stability regression test passed.")
