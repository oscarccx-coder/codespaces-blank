from pathlib import Path

source = Path(__file__).with_name("main.py").read_text(encoding="utf-8")

assert 'self.hub_edit_btn.setCheckable(True)' in source
assert 'self.hub_edit_btn.clicked.connect(self.toggle_hub_edit_mode)' in source
assert 'self.hub_edit_btn.setChecked(bool(self.hub_edit_mode))' in source
assert 'edit_direct_btn = QPushButton("Edit Hub Directly")' in source
assert 'edit_direct_btn.clicked.connect(open_direct_editor)' in source
assert 'self.toggle_hub_edit_mode(True)' in source

print("Hub edit activation regression test passed.")
