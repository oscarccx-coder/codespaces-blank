from pathlib import Path
src = (Path(__file__).resolve().parent / 'modules' / 'voice_imprint_trainer' / 'module.py').read_text(encoding='utf-8')
assert 'required": ["source_path", "profile_name"]' in src
assert 'required": ["source_path", "profile_name", "rights_confirmed"]' not in src
assert 'Voice import requires confirmation' not in src
assert 'Profile lacks rights confirmation' not in src
assert 'Voice profile has no rights/permission confirmation' not in src
assert 'rights.isChecked()' not in src
assert 'personal_use_mode' in src
assert 'Personal-use mode' in src
print('Voice personal-use mode regression passed.')
