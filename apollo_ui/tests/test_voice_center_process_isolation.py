from pathlib import Path
import ast, json
ROOT = Path(__file__).resolve().parents[1]
VOICE = (ROOT/'modules/voice_imprint_trainer/module.py').read_text(encoding='utf-8')
WORKER = (ROOT/'modules/voice_imprint_trainer/xtts_worker.py').read_text(encoding='utf-8')
TTS = (ROOT/'modules/text_to_speech/module.py').read_text(encoding='utf-8')
CENTER = (ROOT/'modules/voice_center/module.py').read_text(encoding='utf-8')
for source in (VOICE, WORKER, TTS, CENTER): ast.parse(source)

assert 'process_isolation' in VOICE
assert '_xtts_worker_request' in VOICE
assert 'BELOW_NORMAL_PRIORITY_CLASS' in VOICE
assert 'unload_xtts_worker' in VOICE
assert 'importlib.util.find_spec' in VOICE
assert 'APOLLO_XTTS_JSON ' in WORKER
assert 'torch.set_num_threads' in WORKER
assert 'torch.inference_mode' in WORKER
assert 'enable_text_splitting=False' in WORKER
assert 'gpt_max_text_tokens' in WORKER
assert 'conditioning_cache' in WORKER
assert '_imprint_active_cache' in TTS
assert 'ApolloVoiceList' in TTS
assert 'Voice Control & Selection' in CENTER
assert 'Voice Imprint Lab' in CENTER
assert 'Performance' in CENTER

for rel in ('modules/text_to_speech/manifest.json','modules/voice_imprint_trainer/manifest.json'):
    data=json.loads((ROOT/rel).read_text(encoding='utf-8'))
    assert data['ui']['enabled'] is False
    assert data['ui']['replacement']=='voice_center'
center=json.loads((ROOT/'modules/voice_center/manifest.json').read_text(encoding='utf-8'))
assert center['ui']['enabled'] is True
print('Voice Center + XTTS process isolation regression passed.')
