"""Owner-enabled offline wake-word service used by Apollo's Chat UI."""
import json
from pathlib import Path
from apollo_wake_word import WakeWordMonitor, normalize_wake_word


class Module:
    def __init__(self, context=None):
        context = context or {}
        self.base = Path(context.get('base_dir', '.')).resolve()
        self.runtime = context.get('runtime')
        self.path = self.base / 'storage' / 'state' / 'voice_agent.json'
        self.monitor = WakeWordMonitor()
        self.owner_enabled = False
        self.wake_word = self._settings()['wake_word']

    def tools(self):
        return [
            {'name': 'get_voice_agent_settings', 'description': 'Read wake-word settings and microphone status.', 'parameters': {'type': 'object', 'properties': {}}},
            {'name': 'set_voice_agent_settings', 'description': 'Set the wake phrase. Microphone opt-in belongs to the owner UI.', 'parameters': {'type': 'object', 'properties': {'wake_word': {'type': 'string'}, 'enabled': {'type': 'boolean'}, 'listen_seconds': {'type': 'integer'}}}},
            {'name': 'start_listening', 'description': 'Resume wake listening only after the owner enables it in the UI.', 'parameters': {'type': 'object', 'properties': {}}},
            {'name': 'stop_listening', 'description': 'Stop wake listening and release the microphone.', 'parameters': {'type': 'object', 'properties': {}}},
        ]

    def _settings(self):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            word = normalize_wake_word(data.get('wake_word', 'apollo'))
        except (OSError, ValueError, TypeError, AttributeError): word = 'apollo'
        return {'wake_word': word, 'enabled': self.owner_enabled, 'listen_seconds': 8, 'status': self.monitor.snapshot()}

    def enable_from_ui(self, enabled):
        if not enabled:
            self.owner_enabled = False; self.monitor.stop(); return
        if self.runtime and self.runtime.get_permission('voice_agent__start_listening') != 'allow':
            raise PermissionError('Wake-word microphone use is blocked in Apollo permissions.')
        self.wake_word = self._settings()['wake_word']
        self.monitor.start(self.wake_word)
        self.owner_enabled = True

    def run(self, action, arguments):
        arguments = arguments or {}
        if action == 'get_voice_agent_settings': return self._settings()
        if action == 'stop_listening':
            self.enable_from_ui(False); return {'stopped': True}
        if action == 'start_listening':
            if not self.owner_enabled: raise PermissionError('Enable Wake word in Apollo Chat first.')
            # The UI controller owns pause/resume during replies and privacy.
            return {'started': self.monitor.snapshot()['running'], 'status': self.monitor.snapshot()}
        if action == 'set_voice_agent_settings':
            if arguments.get('enabled'): raise PermissionError('Enable Wake word in Apollo Chat; tools cannot opt in to the microphone.')
            if self.owner_enabled: raise RuntimeError('Turn off Wake word before changing its phrase.')
            config = {'wake_word': normalize_wake_word(arguments.get('wake_word', self._settings()['wake_word']))}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix('.json.tmp')
            temp.write_text(json.dumps(config, indent=2), encoding='utf-8'); temp.replace(self.path)
            self.wake_word = config['wake_word']
            return self._settings()
        raise KeyError(action)

    def close(self):
        self.owner_enabled = False; self.monitor.close()

    def self_test(self):
        assert normalize_wake_word(' Apollo ') == 'apollo'
        assert not self.owner_enabled
        return 'Owner-enabled offline wake-word contracts passed'
