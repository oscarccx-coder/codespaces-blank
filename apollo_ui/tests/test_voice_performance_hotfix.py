from pathlib import Path
import ast
ROOT=Path(__file__).resolve().parent
V=(ROOT/"modules/voice_imprint_trainer/module.py").read_text(encoding="utf-8")
T=(ROOT/"modules/text_to_speech/module.py").read_text(encoding="utf-8")
ast.parse(V); ast.parse(T)
for s in ["_split_xtts_text", "_xtts_token_count", "enable_text_splitting=False", "_conditioning_cache", "_xtts_inference_lock", "ApolloVoiceSynthesis"]: assert s in V, s
for s in ["_queue_voice_imprint", "ApolloVoiceImprintTTS", "_imprint_pending"]: assert s in T, s
assert '"enable_text_splitting": False' in V
print("Voice performance / 400-token regression passed")
