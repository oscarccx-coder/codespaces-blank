"""Main-thread coordination of the Voice Agent and Apollo's chat composer."""
import time


class ChatWakeController:
    def __init__(self, owner):
        self.owner = owner
        self.agent = None
        self.target = None
        self.hold_until = 0.0

    @property
    def enabled(self): return bool(self.agent is not None and self.agent.owner_enabled)

    @property
    def capturing(self):
        return self.enabled and self.agent.monitor.snapshot()['state'] == 'capturing'

    @property
    def microphone_open(self):
        return bool(self.agent is not None and self.agent.monitor.snapshot().get('microphone_open'))

    def pause(self):
        if self.agent is not None: self.agent.monitor.set_paused(True)
        self.target = None

    def close(self):
        self.target = None
        if self.agent is not None: self.agent.close()

    def enable(self, enabled):
        if not enabled and self.agent is not None:
            self.agent.enable_from_ui(False); self.target = None; return
        record = self.owner.module_manager.get_module('voice_agent')
        agent = record.get('instance') if record and record.get('enabled') else None
        if agent is None: raise RuntimeError('Enable the Voice Agent module to use Wake word.')
        agent.enable_from_ui(bool(enabled))
        self.agent = agent; self.target = None

    def pump(self, speech):
        owner = self.owner
        workspace = getattr(owner, 'chat_workspace', None)
        if workspace is None: return
        header = workspace.core_header
        record = owner.module_manager.get_module('voice_agent')
        agent = record.get('instance') if record and record.get('enabled') else None
        if self.agent is not None and self.agent is not agent:
            self.agent.enable_from_ui(False); self.agent = None
        if agent is None:
            if hasattr(owner, 'wake_status_button'): owner.wake_status_button.hide()
            header.set_wake_status(False, 'Enable Voice Agent module', False); return
        snapshot = agent.monitor.snapshot()
        word = agent.wake_word if isinstance(agent.wake_word, str) else 'apollo'
        header.wake.setText('Wake word: ' + word.title())
        enabled = bool(agent.owner_enabled)
        temporary = bool(workspace.session_store.temporary)
        speech_busy = bool(speech.get('playing') or speech.get('generating') or owner.speech_task is not None)
        if speech_busy: self.hold_until = time.monotonic() + .8
        reason = ('Temporary chat' if temporary else 'Apollo is replying' if owner.chat_busy or speech_busy
                  else 'Dictation active' if owner.stt_task is not None or owner._stt_waiting_for_wake
                  else 'Reading files' if workspace.io_busy else 'Reply echo guard' if time.monotonic() < self.hold_until else '')
        if enabled and owner.runtime.get_permission('voice_agent__start_listening') != 'allow':
            agent.enable_from_ui(False); enabled = False
            owner.statusBar().showMessage('Wake-word microphone permission was revoked.', 10000)
        if enabled and snapshot['state'] == 'error':
            error = snapshot['error']
            agent.enable_from_ui(False); enabled = False
            owner._core_error = (error, time.monotonic() + 12)
            owner.statusBar().showMessage(error, 12000)
        events = agent.monitor.drain_events()
        if enabled and not reason and not owner._closing:
            for event in events:
                if event['kind'] == 'wake':
                    self.target = (workspace.session_store, workspace.chat_id)
                    if owner.isMinimized(): owner.showNormal()
                    owner.switch_page('Chat')
                    workspace.status.setText(word.title() + ' heard you · speak your message after the wake phrase.')
                elif event['kind'] == 'command':
                    target = self.target; self.target = None
                    if target != (workspace.session_store, workspace.chat_id):
                        workspace.status.setText('Voice message discarded because the active chat changed.'); continue
                    text = event.get('text', '').strip()
                    if text:
                        draft = workspace.composer.text().rstrip()
                        workspace.composer.setText((draft + '\n' if draft else '') + text)
                        workspace.composer.setFocus()
                        workspace.status.setText('Voice message ready · review it, then Send.')
                    else:
                        workspace.status.setText('No message recognized · say ' + word.title() + ', pause, then speak again.')
                    self.hold_until = time.monotonic() + .8
                    reason = 'Message ready'
        if enabled: agent.monitor.set_paused(bool(reason) or owner._closing)
        state = agent.monitor.snapshot()['state']
        text = ('Off · microphone closed' if not enabled else 'Paused · ' + reason if reason
                else 'Microphone on · speak now' if state == 'capturing'
                else 'Microphone on · say ' + word.title() if state == 'listening' else 'Starting microphone…')
        if not snapshot['supported']: text = 'Requires Windows speech'
        header.set_wake_status(enabled, text, snapshot['supported'] and not temporary)
        if hasattr(owner, 'wake_status_button'):
            owner.wake_status_button.setVisible(enabled)
            owner.wake_status_button.setText(('Wake word paused' if reason else 'Microphone on') + ' · Stop wake word')
