"""Owner setup/preferences UI; chat has no install or backend-switch action."""
import json
import sys
import threading


def build_view(module,parent=None):
    from PySide6.QtCore import QObject,Signal,QProcess
    from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,QPlainTextEdit,QMessageBox,QLineEdit
    class Signals(QObject): result=Signal(str)
    page=QWidget(parent);layout=QVBoxLayout(page);signals=Signals(page);svc=module.service
    layout.addWidget(QLabel('Open-source backends · shared Apollo abilities'))
    layout.addWidget(QLabel('Choose what to install. Model downloads, graph services and Docker readiness are checked separately.'))
    selection=QComboBox();selection.addItems(list(svc.sources));layout.addWidget(selection)
    row=QHBoxLayout();setup=QPushButton('Install / repair selected');check=QPushButton('Refresh status');stop=QPushButton('Stop active task')
    for button in (setup,check,stop): row.addWidget(button)
    layout.addLayout(row)
    boxes={};current=svc.settings()
    for key,caption,items in [('voice','Speech output',['existing','kokoro','voicestudio']),('transcription','Dictation',['existing','faster_whisper']),
                              ('web','Web page reader',['existing','crawl4ai']),('device','Worker device',['cpu','cuda'])]:
        row=QHBoxLayout();row.addWidget(QLabel(caption));combo=QComboBox();combo.addItems(items);combo.setCurrentText(current[key]);boxes[key]=combo;row.addWidget(combo);layout.addLayout(row)
    voice=QLineEdit(current['voice_name']);voice.setPlaceholderText('Kokoro voice, e.g. bm_george');layout.addWidget(voice)
    layout.addWidget(QLabel('VoiceStudio (separate local app, no XTTS required)'))
    vs_url=QLineEdit(current['voicestudio_url']);vs_url.setPlaceholderText('http://127.0.0.1:3900');layout.addWidget(vs_url)
    vs_voice=QLineEdit(current['voicestudio_voice']);vs_voice.setPlaceholderText('VoiceStudio profile ID or default');layout.addWidget(vs_voice)
    vs_model=QLineEdit(current['voicestudio_model']);vs_model.setPlaceholderText('tts-1 = active engine in VoiceStudio');layout.addWidget(vs_model)
    probe_voice=QPushButton('Test VoiceStudio connection');layout.addWidget(probe_voice)
    llama=QLineEdit(current['llama_url']);llama.setPlaceholderText('Local llama-server URL ending /v1');layout.addWidget(llama)
    save=QPushButton('Save backend choices');layout.addWidget(save)
    activate=QPushButton('Use running llama.cpp server for Apollo chat');layout.addWidget(activate)
    history=QPushButton('Saved task receipts');layout.addWidget(history)
    output=QPlainTextEdit();output.setReadOnly(True);output.document().setMaximumBlockCount(2000);layout.addWidget(output,1)
    signals.result.connect(output.appendPlainText)
    def show(): output.setPlainText(json.dumps(svc.status(),indent=2))
    def save_choices():
        try:
            for key,name in [('voice','kokoro'),('transcription','faster_whisper'),('web','crawl4ai')]:
                if boxes[key].currentText()==name and not svc.status(name)['installed']:
                    raise RuntimeError('Install '+name+' before selecting it')
            svc.configure(**{k:v.currentText() for k,v in boxes.items()},
                          voice_name=voice.text().strip(),llama_url=llama.text().strip(),
                          voicestudio_url=vs_url.text().strip(),voicestudio_voice=vs_voice.text().strip(),
                          voicestudio_model=vs_model.text().strip())
            show()
        except Exception as exc: output.appendPlainText(str(exc))
    def background(fn):
        def work():
            try: signals.result.emit(json.dumps(fn(),indent=2,default=str))
            except Exception as exc: signals.result.emit(f'{type(exc).__name__}: {exc}')
        threading.Thread(target=work,daemon=True).start()
    def test_voice():
        chosen=vs_url.text().strip()
        from apollo_voicestudio import probe
        background(lambda:probe(chosen))

    def activate_llama():
        # Capture text before leaving GUI thread.
        chosen=llama.text().strip()
        from apollo_capability_policy import local_endpoint
        try: local_endpoint(chosen)
        except Exception as exc: output.appendPlainText(str(exc));return
        # Model discovery and config writes run off the GUI thread.
        def apply():
            from ollama_client import OllamaClient
            from apollo_config import ApolloConfigStore
            if not chosen.endswith('/v1'): raise ValueError('URL must end with /v1')
            models=OllamaClient(chosen,'local').models()
            if not models: raise RuntimeError('Start llama-server with a GGUF model first')
            config_store=ApolloConfigStore(module.base);config=config_store.load()
            from apollo_capabilities import atomic_json
            atomic_json(svc.home/'previous_model_settings.json',{'ollama_url':config['ollama_url'],'model':config['model']})
            config.update(ollama_url=chosen,model=models[0]);config_store.save_user(config)
            return {'saved':True,'notice':'Restart Apollo. Restore Ollama URL and model in Settings to switch back.'}
        background(apply)
    def install():
        name=selection.currentText()
        if QMessageBox.question(page,'Install backend',f'Download {name} from its pinned GitHub revision and install its dependencies on Apollo’s drive?')!=QMessageBox.Yes:return
        if getattr(sys,'frozen',False): output.appendPlainText('Run Setup/20_SETUP_CAPABILITIES.bat '+name);return
        process=QProcess(page);page.setup_process=process;setup.setEnabled(False)
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(lambda:output.appendPlainText(bytes(process.readAllStandardOutput()).decode('utf-8','replace')))
        process.finished.connect(lambda code,*_: (setup.setEnabled(True),output.appendPlainText('Setup finished' if code==0 else 'Setup failed; see log')))
        process.errorOccurred.connect(lambda _:(setup.setEnabled(True),output.appendPlainText(process.errorString())))
        runner=sys.executable;prefix=[]
        if not (3,12)<=sys.version_info[:2]<=(3,13):
            import shutil
            if sys.platform=='win32' and shutil.which('py'): runner='py';prefix=['-3.13']
            else:
                runner=shutil.which('python3.12') or shutil.which('python3.13')
                if not runner:
                    setup.setEnabled(True);output.appendPlainText('Install Python 3.12/3.13 and run the numbered Setup batch file.');return
        process.start(runner,prefix+[str(module.base/'tools/setup_capabilities.py'),name])
    save.clicked.connect(save_choices);activate.clicked.connect(activate_llama);setup.clicked.connect(install)
    probe_voice.clicked.connect(test_voice)
    check.clicked.connect(show);stop.clicked.connect(lambda:background(lambda:(svc.cancel(),{'stop_requested':True})[1]))
    history.clicked.connect(lambda:background(svc.runs));show();return page
