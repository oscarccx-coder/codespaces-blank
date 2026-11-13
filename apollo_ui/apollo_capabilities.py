"""On-demand backends shared by Apollo's existing systems.

Installation/configuration are owner UI/CLI actions, never model-callable tools.
Each library has its own pinned Git checkout and Python environment.
"""
from __future__ import annotations
import json
import hashlib
import contextvars
import os
from pathlib import Path
import subprocess
import threading
import time
import uuid
from apollo_capability_policy import local_endpoint, public_url

ROOT = Path(__file__).resolve().parent
OPERATIONS = {'docling': {'document'}, 'kokoro': {'synthesize'}, 'faster_whisper': {'transcribe'},
    'crawl4ai': {'crawl'}, 'browser_use': {'browser_task'}, 'gpt_researcher': {'research'},
    'graphiti': {'graph_search', 'graph_add'}, 'llama_cpp': {'inference'}}
DEFAULTS = {'voice': 'existing', 'transcription': 'existing', 'web': 'existing',
    'device': 'cpu', 'voice_name': 'bm_george', 'whisper_model': 'base.en',
    'embedding_model': 'nomic-embed-text', 'graph_uri': 'bolt://127.0.0.1:7687',
    'graph_user': 'neo4j', 'llama_url': 'http://127.0.0.1:8080/v1',
    'timeout': 180, 'research_timeout': 600, 'max_steps': 12}
OWNER = contextvars.ContextVar("apollo_capability_owner", default=None)


def cancel_owned(owner):
    with _SERVICES_LOCK: active = list(_SERVICES.values())
    for backend in active:
        if backend.container:
            threading.Thread(target=backend.cancel,kwargs={"expected_owner":owner},daemon=True).start()
        else: backend.cancel(expected_owner=owner)


_SERVICES = {}; _SERVICES_LOCK = threading.Lock()


def atomic_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(value, indent=2, default=str), encoding='utf-8'); os.replace(temp, path)
    finally: temp.unlink(missing_ok=True)


def service(base, runtime=None):
    key = str(Path(base).resolve())
    with _SERVICES_LOCK:
        if key not in _SERVICES: _SERVICES[key] = CapabilityService(key)
        if runtime is not None: _SERVICES[key].runtime = runtime
        return _SERVICES[key]


class CapabilityService:
    def __init__(self, base):
        self.base = Path(base).resolve(); self.runtime = None
        self.home = self.base / 'storage' / 'integrations'
        self.config_path = self.base / 'storage/state/capability_backends.json'
        self.lock = threading.Lock(); self.state_lock = threading.Lock()
        self.process = None; self.active = None; self.container = None; self.active_backend = None; self.owner = None
        self.cancelled = threading.Event()
        self.sources = json.loads((ROOT / 'integrations/sources.lock.json').read_text())
        self.adapter_fingerprint = hashlib.sha256((ROOT/'apollo_capability_worker.py').read_bytes()+(ROOT/'apollo_capability_policy.py').read_bytes()).hexdigest()[:12]

    def settings(self):
        try: saved = json.loads(self.config_path.read_text(encoding='utf-8'))
        except FileNotFoundError: saved = {}
        if not isinstance(saved, dict): raise ValueError('Malformed capability settings')
        return {**DEFAULTS, **saved}

    def configure(self, **changes):
        # Called by owner UI only. No configuration action is exported to chat.
        if set(changes) - set(DEFAULTS): raise ValueError('Unknown backend setting')
        for key, choices in {'voice': {'existing','kokoro'}, 'transcription': {'existing','faster_whisper'},
                             'web': {'existing','crawl4ai'}, 'device': {'cpu','cuda'}}.items():
            if key in changes and changes[key] not in choices: raise ValueError(key)
        for key in ('timeout', 'research_timeout', 'max_steps'):
            if key in changes:
                changes[key] = max(1, min(int(changes[key]), 900 if key != 'max_steps' else 30))
        if 'llama_url' in changes: local_endpoint(changes['llama_url'])
        if 'graph_uri' in changes:
            from urllib.parse import urlsplit
            if urlsplit(changes['graph_uri']).hostname not in {'localhost','127.0.0.1','::1'}:
                raise PermissionError('Graph storage must be local')
        saved = {**self.settings(), **changes}; atomic_json(self.config_path, saved); return saved

    def python(self, name):
        return self.home / 'environments' / name / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')

    def status(self, name=None):
        result = {}
        for key, source in self.sources.items():
            try: receipt = json.loads((self.home / 'receipts' / (key + '.json')).read_text())
            except (OSError, ValueError): receipt = {}
            installed = receipt.get('sha') == source['sha']
            if key == 'browser_use': installed = installed and receipt.get('image') == self.image()
            elif key == 'llama_cpp': installed = installed and Path(receipt.get('binary', '')).is_file()
            else: installed = installed and self.python(key).is_file()
            result[key] = {'installed': bool(installed), 'source': 'https://github.com/' + source['repository'],
                           'revision': source['sha'], 'license': source['license'],
                           'notice': 'Dependencies installed; models/services and first real task still require readiness checks' if installed else 'Not installed: use Capabilities setup',
                           'setup': f'Setup/20_SETUP_CAPABILITIES.bat {key}'}
        return result[name] if name else {'backends': result, 'settings': self.settings(), 'active': self.active}

    def image(self): return 'apollo-browser-use:' + self.sources['browser_use']['sha'][:12] + '-' + self.adapter_fingerprint

    def cancel(self, expected_owner=None):
        with self.state_lock:
            if expected_owner is not None and self.owner is not expected_owner: return
            self.cancelled.set()
            proc, container = self.process, self.container
        if container:
            try: subprocess.run(['docker','kill',container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            except (OSError, subprocess.TimeoutExpired): pass
        if proc and proc.poll() is None:
            try: proc.terminate()
            except OSError: pass

    def input_file(self, value):
        path = Path(value).resolve()
        if not path.is_relative_to(self.base): raise PermissionError('Use a file inside Apollo roots')
        if not path.is_file(): raise FileNotFoundError(str(path))
        if path.stat().st_size > 50 * 1024 * 1024: raise ValueError('Input exceeds 50 MiB')
        return str(path)

    def model_settings(self):
        from apollo_config import ApolloConfigStore
        config = ApolloConfigStore(self.base).load()
        url = local_endpoint(config['ollama_url'])
        if 'cloud' in config['model'].lower(): raise PermissionError('Select a local model')
        return {'url': url.removesuffix('/v1'), 'model': config['model'], 'provider':'openai' if url.endswith('/v1') else 'ollama'}

    def run(self, name, operation, arguments=None, *, timeout=None):
        if operation not in OPERATIONS.get(name, set()): raise ValueError('Unsupported backend operation')
        if not self.status(name)['installed']: raise RuntimeError(self.status(name)['setup'] + ' must finish first')
        if not self.lock.acquire(False): raise RuntimeError('A heavy capability is already running; wait or stop it')
        ident = uuid.uuid4().hex; started = time.time(); proc = None
        with self.state_lock:
            self.cancelled.clear(); self.owner = OWNER.get()
        job = {'id': ident, 'backend': name, 'operation': operation, 'state': 'running', 'started': started}
        receipt = self.home / 'runs' / (ident + '.json')
        try:
            settings = self.settings(); args = dict(arguments or {})
            if getattr(self.owner, "_cancelled", False):
                self.cancelled.set(); raise RuntimeError("Capability cancelled")
            if operation in {'document','transcribe'}: args['path'] = self.input_file(args['path'])
            if operation == 'crawl': args['url'] = public_url(args['url'])
            if operation in {'research','browser_task','graph_search','graph_add'}:
                args['model_config'] = self.model_settings()
            if operation in {'research','browser_task','graph_search','inference'}:
                if not str(args.get('query','')).strip() or len(str(args['query']))>12000:
                    raise ValueError('Supply a query of 1–12000 characters')
            if operation == 'research':
                sources=args.get('sources')
                if not isinstance(sources,list) or not 1<=len(sources)<=8:
                    raise ValueError('Supply 1–8 evidence URLs for bounded research')
                args['sources'] = [public_url(url) for url in sources]
            if operation == 'browser_task':
                # Browser Use 1.x executes generated Python. It must never run in Apollo's host process.
                if not isinstance(args.get('domains'),list) or not 1<=len(args['domains'])<=12:
                    raise ValueError('Supply 1–12 public domains this browser task may visit')
                args['domains'] = [__import__('urllib.parse', fromlist=['urlsplit']).urlsplit(public_url('https://' + str(d))).hostname for d in args['domains']][:12]
                from urllib.parse import urlsplit
                model_url = urlsplit(args['model_config']['url'])
                args['model_config']['url'] = f'http://host.docker.internal:{model_url.port or 11434}'
            if operation == 'inference': args['url'] = local_endpoint(settings['llama_url'])
            args['settings'] = settings
            output_dir = self.home / 'outputs' / ident; output_dir.mkdir(parents=True)
            args['output_dir'] = str(output_dir)
            if operation in {'graph_search','graph_add'}:
                from urllib.parse import urlsplit
                if urlsplit(settings['graph_uri']).hostname not in {'localhost','127.0.0.1','::1'}:
                    raise PermissionError('Graph storage must be local')
                secret = self.home / 'graph_credentials.json'
                if not secret.is_file(): raise RuntimeError('Set local graph credentials in storage/integrations/graph_credentials.json')
                args['graph_credentials'] = json.loads(secret.read_text())
            args['settings'] = dict(settings)
            args['settings']['model_cache'] = str(self.home / 'models')
            command = [str(self.python(name)), '-u', str(ROOT / 'apollo_capability_worker.py')]
            env = {k:v for k,v in os.environ.items() if k.upper() in {'PATH','SYSTEMROOT','WINDIR','TEMP','TMP','COMSPEC','PATHEXT','LD_LIBRARY_PATH'}}
            env['VIRTUAL_ENV'] = str(self.home / 'environments' / name)
            env['PATH'] = str(self.python(name).parent) + os.pathsep + env.get('PATH','')
            cache = self.home / 'models'; cache.mkdir(parents=True, exist_ok=True)
            env.update(HOME=str(self.home), USERPROFILE=str(self.home), HF_HOME=str(cache / 'huggingface'),
                TORCH_HOME=str(cache / 'torch'), PLAYWRIGHT_BROWSERS_PATH=str(self.home / 'browsers'),
                ANONYMIZED_TELEMETRY='false', POSTHOG_DISABLED='true', DO_NOT_TRACK='1', OPENAI_API_KEY='local-only', PYTHONUNBUFFERED='1')
            container = None
            if name == 'browser_use':
                container = 'apollo-browser-' + ident
                command = ['docker','run','--rm','-i','--name',container,'--init','--cap-drop=ALL',
                    '--security-opt=no-new-privileges','--read-only','--pids-limit=256','--memory=3g','--cpus=2',
                    '--tmpfs','/tmp:rw,nosuid,size=1g','--shm-size=256m',
                    '--add-host=host.docker.internal:host-gateway',self.image()]
                args['output_dir'] = '/tmp/output'
                env = None  # Docker CLI uses the owner's daemon context; container gets only its Dockerfile environment.
            atomic_json(receipt, job)
            if self.runtime: self.runtime.publish('capability.started', 'capabilities', job)
            with (output_dir / 'worker.log').open('w', encoding='utf-8') as log:
                proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                    text=True, encoding='utf-8', cwd=output_dir, env=env,
                    **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
                with self.state_lock: self.process, self.active, self.container, self.active_backend = proc, ident, container, name
                if self.cancelled.is_set(): proc.terminate()
                limit = max(1, int(timeout or settings['research_timeout' if name == 'gpt_researcher' else 'timeout'])-int(time.time()-started))
                wire = json.dumps({'backend': name, 'operation': operation, 'arguments': args})
                try: stdout, _ = proc.communicate(wire, timeout=limit)
                except subprocess.TimeoutExpired:
                    self.cancel(); proc.communicate(timeout=15); raise TimeoutError('Capability reached its time budget')
            if self.cancelled.is_set(): raise RuntimeError('Capability cancelled')
            if len(stdout) > 4 * 1024 * 1024: raise ValueError('Worker response exceeds 4 MiB')
            if proc.returncode: raise RuntimeError('Backend failed; inspect ' + str(output_dir / 'worker.log'))
            result = json.loads(stdout)
            if 'error' in result: raise RuntimeError(result['error'])
            job.update(state='completed' if result.get('completed',True) else 'blocked', result=result, duration=round(time.time()-started, 3))
            atomic_json(receipt, job)
            if self.runtime: self.runtime.publish('capability.completed','capabilities',job)
            return {**result, 'run_id':ident, 'backend':name, 'source_revision':self.sources[name]['sha']}
        except Exception as exc:
            job.update(state='cancelled' if self.cancelled.is_set() else 'failed', error=str(exc), duration=round(time.time()-started, 3))
            atomic_json(receipt, job)
            if self.runtime: self.runtime.publish('capability.failed','capabilities',job)
            raise
        finally:
            try:
                if proc and proc.poll() is None:
                    proc.kill(); proc.wait(timeout=10)
            finally:
                with self.state_lock: self.process = self.active = self.container = self.active_backend = self.owner = None
                self.lock.release()

    def runs(self):
        result = []
        for path in sorted((self.home / 'runs').glob('*.json'), reverse=True):
            try:
                value=json.loads(path.read_text())
                if value['state']=='running' and value['id']!=self.active:
                    value.update(state='interrupted',error='Previous run ended without a completion receipt; review outputs before retrying')
                    atomic_json(path,value)
                result.append(value)
            except (OSError, ValueError): pass
        return sorted(result, key=lambda r:r['started'], reverse=True)[:30]
