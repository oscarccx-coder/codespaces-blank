from pathlib import Path
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ast
import hashlib
import hmac
import json
import os
import platform
import secrets
import socket
import subprocess
import threading
import time
import uuid
from urllib.parse import urlparse

from apollo_storage import StorageLayout
from apollo_update import UpdateService
from ollama_client import OllamaClient


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def _sha(data):
    return hashlib.sha256(data or b'').hexdigest()


def sign_request(token, method, path, body=b'', timestamp=None, request_id=None):
    timestamp = str(timestamp or int(time.time()))
    request_id = str(request_id or uuid.uuid4())
    canonical = '\n'.join([
        str(method).upper(), str(path), timestamp, request_id, _sha(body)
    ]).encode('utf-8')
    signature = hmac.new(str(token).encode('utf-8'), canonical, hashlib.sha256).hexdigest()
    return {
        'X-Apollo-Timestamp': timestamp,
        'X-Apollo-Request-ID': request_id,
        'X-Apollo-Signature': signature,
    }


class DeviceAgentService:
    """Authenticated LAN worker for Apollo Fleet and Cluster.

    Only allow-listed task types are exposed. This is intentionally not a
    remote shell and cannot execute arbitrary Python supplied over the network.
    """

    def __init__(self, base_dir):
        self.base = Path(base_dir).resolve()
        self.storage = StorageLayout(self.base)
        self.storage.ensure_layout()
        self.state_dir = self.storage.state / 'fleet'
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.state_dir / 'device_agent.json'
        self.tasks_path = self.state_dir / 'worker_tasks.json'
        self._lock = threading.RLock()
        self._server = None
        self._thread = None
        self._tasks = {}
        self._cancelled = set()
        self._seen_request_ids = {}
        self._ensure_config()
        self._load_tasks()

    def _ensure_config(self):
        try:
            data = json.loads(self.config_path.read_text(encoding='utf-8')) if self.config_path.exists() else {}
        except Exception:
            data = {}
        update_device = UpdateService(self.base).device()
        defaults = {
            'device_id': update_device.get('device_id') or str(uuid.uuid4()),
            'device_name': update_device.get('device_name') or socket.gethostname() or 'Apollo Device',
            'host': '0.0.0.0',
            'port': 8766,
            'auto_start': False,
            'role': 'worker',
            'group': 'Default',
            'auth_token': secrets.token_urlsafe(32),
        }
        changed = False
        for key, value in defaults.items():
            if key not in data or data.get(key) in (None, ''):
                data[key] = value
                changed = True
        if changed or not self.config_path.exists():
            _write_json(self.config_path, data)

    def config(self):
        return json.loads(self.config_path.read_text(encoding='utf-8'))

    def configure(self, **updates):
        data = self.config()
        for key in ('device_name', 'host', 'role', 'group'):
            if key in updates and updates[key] is not None and str(updates[key]).strip():
                data[key] = str(updates[key]).strip()
        if 'port' in updates and updates['port'] is not None:
            port = int(updates['port'])
            if port < 0 or port > 65535:
                raise ValueError('port must be 0-65535')
            data['port'] = port
        if 'auto_start' in updates and updates['auto_start'] is not None:
            data['auto_start'] = bool(updates['auto_start'])
        _write_json(self.config_path, data)
        return self.status()

    def enrollment_token(self):
        return self.config()['auth_token']

    def rotate_token(self):
        data = self.config()
        data['auth_token'] = secrets.token_urlsafe(32)
        _write_json(self.config_path, data)
        return data['auth_token']

    def _load_tasks(self):
        try:
            data = json.loads(self.tasks_path.read_text(encoding='utf-8')) if self.tasks_path.exists() else {}
            if isinstance(data, dict):
                self._tasks = data
        except Exception:
            self._tasks = {}

    def _save_tasks(self):
        items = sorted(self._tasks.items(), key=lambda p: str(p[1].get('created_at', '')), reverse=True)[:200]
        _write_json(self.tasks_path, dict(items))

    def _hardware(self):
        total = available = None
        try:
            import psutil
            vm = psutil.virtual_memory()
            total = round(vm.total / (1024**3), 2)
            available = round(vm.available / (1024**3), 2)
        except Exception:
            pass
        gpu = None
        vram_free_mb = None
        try:
            proc = subprocess.run([
                'nvidia-smi', '--query-gpu=name,memory.free', '--format=csv,noheader,nounits'
            ], capture_output=True, text=True, timeout=2)
            if proc.returncode == 0 and proc.stdout.strip():
                bits = [x.strip() for x in proc.stdout.strip().splitlines()[0].split(',')]
                gpu = bits[0]
                if len(bits) > 1:
                    vram_free_mb = int(float(bits[1]))
        except Exception:
            pass
        return {
            'cpu_count': os.cpu_count(),
            'ram_total_gb': total,
            'ram_available_gb': available,
            'gpu': gpu,
            'vram_free_mb': vram_free_mb,
        }

    def _ollama(self):
        cfg = json.loads((self.base / 'config.json').read_text(encoding='utf-8'))
        client = OllamaClient(
            cfg.get('ollama_url', 'http://127.0.0.1:11434'),
            cfg.get('model', ''),
            cfg.get('temperature', 0.65),
            cfg.get('num_ctx', 8192),
        )
        return client, cfg

    def capabilities(self):
        caps = ['task_worker', 'ping', 'sha256_text', 'json_validate', 'python_syntax', 'workspace_file_hash']
        try:
            client, _ = self._ollama()
            if client.is_running():
                caps.append('ollama_prompt')
        except Exception:
            pass
        if self._hardware().get('gpu'):
            caps.append('cuda')
        return sorted(set(caps))

    def identity(self):
        cfg = self.config()
        return {
            'device_id': cfg['device_id'],
            'device_name': cfg['device_name'],
            'role': cfg.get('role', 'worker'),
            'group': cfg.get('group', 'Default'),
            'platform': platform.system().lower(),
            'architecture': platform.machine().lower(),
            'agent_version': '1.0.0',
        }

    def actual_port(self):
        if self._server is not None:
            return int(self._server.server_address[1])
        return int(self.config().get('port', 8766))

    def status(self):
        try:
            version = str(json.loads((self.base / 'config.json').read_text(encoding='utf-8')).get('version', '0'))
        except Exception:
            version = '0'
        counts = {}
        with self._lock:
            for task in self._tasks.values():
                state = str(task.get('status', 'unknown'))
                counts[state] = counts.get(state, 0) + 1
        return {
            **self.identity(),
            'apollo_version': version,
            'health': 'healthy',
            'agent_running': self._server is not None,
            'listen_port': self.actual_port(),
            'capabilities': self.capabilities(),
            'hardware': self._hardware(),
            'task_counts': counts,
            'updated_at': _utc_now(),
        }

    def _cleanup_seen(self):
        cutoff = time.time() - 180
        for key, created in list(self._seen_request_ids.items()):
            if created < cutoff:
                self._seen_request_ids.pop(key, None)

    def verify_request(self, method, path, headers, body=b''):
        timestamp = str(headers.get('X-Apollo-Timestamp', ''))
        request_id = str(headers.get('X-Apollo-Request-ID', ''))
        supplied = str(headers.get('X-Apollo-Signature', ''))
        if not timestamp or not request_id or not supplied:
            return False, 'missing Apollo authentication headers'
        try:
            if abs(time.time() - float(timestamp)) > 90:
                return False, 'request timestamp outside allowed window'
        except Exception:
            return False, 'invalid request timestamp'
        with self._lock:
            self._cleanup_seen()
            if request_id in self._seen_request_ids:
                return False, 'replayed request id'
        expected = sign_request(
            self.enrollment_token(), method, path, body, timestamp=timestamp, request_id=request_id
        )['X-Apollo-Signature']
        if not hmac.compare_digest(expected, supplied):
            return False, 'invalid request signature'
        with self._lock:
            self._seen_request_ids[request_id] = time.time()
        return True, 'ok'

    def _workspace_path(self, relative):
        root = (self.base / 'workspace').resolve()
        root.mkdir(parents=True, exist_ok=True)
        target = (root / str(relative)).resolve()
        if target != root and root not in target.parents:
            raise ValueError('workspace path escapes workspace')
        return target

    def submit_task(self, envelope):
        if not isinstance(envelope, dict):
            raise ValueError('task envelope must be an object')
        task_type = str(envelope.get('type', '')).strip()
        allowed = {'ping', 'sha256_text', 'json_validate', 'python_syntax', 'workspace_file_hash', 'ollama_prompt'}
        if task_type not in allowed:
            raise ValueError(f'Unsupported task type: {task_type}')
        task_id = str(envelope.get('task_id') or uuid.uuid4())
        lease_seconds = max(10, min(int(envelope.get('lease_seconds', 600)), 3600))
        task = {
            'task_id': task_id,
            'job_id': str(envelope.get('job_id', '')),
            'type': task_type,
            'objective': str(envelope.get('objective', '')),
            'payload': envelope.get('payload') if isinstance(envelope.get('payload'), dict) else {},
            'status': 'queued',
            'created_at': _utc_now(),
            'lease_seconds': lease_seconds,
            'lease_expires_at_epoch': time.time() + lease_seconds,
            'started_at': None,
            'finished_at': None,
            'result': None,
            'error': None,
            'evidence': {},
        }
        with self._lock:
            self._tasks[task_id] = task
            self._save_tasks()
        threading.Thread(target=self._run_task, args=(task_id,), daemon=True, name=f'apollo-worker-{task_id[:8]}').start()
        return {'ok': True, 'task_id': task_id, 'status': 'queued', 'lease_seconds': lease_seconds}

    def task_status(self, task_id):
        with self._lock:
            task = self._tasks.get(str(task_id))
            return dict(task) if task else None

    def cancel_task(self, task_id):
        task_id = str(task_id)
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return {'ok': False, 'error': 'task not found'}
            self._cancelled.add(task_id)
            if task.get('status') == 'queued':
                task['status'] = 'cancelled'
                task['finished_at'] = _utc_now()
                self._save_tasks()
        return {'ok': True, 'task_id': task_id, 'cancel_requested': True}

    def _execute_task(self, task):
        kind = task['type']
        payload = task.get('payload') or {}
        if kind == 'ping':
            return {'pong': True, 'payload': payload}
        if kind == 'sha256_text':
            text = str(payload.get('text', ''))
            return {'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(), 'length': len(text)}
        if kind == 'json_validate':
            value = json.loads(str(payload.get('text', '')))
            return {'valid': True, 'type': type(value).__name__}
        if kind == 'python_syntax':
            code = str(payload.get('code', ''))
            ast.parse(code)
            return {'valid': True, 'lines': len(code.splitlines())}
        if kind == 'workspace_file_hash':
            path = self._workspace_path(payload.get('path', ''))
            if not path.is_file():
                raise FileNotFoundError(path)
            return {
                'path': str(path.relative_to(self.base / 'workspace')).replace('\\', '/'),
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'size': path.stat().st_size,
            }
        if kind == 'ollama_prompt':
            prompt = str(payload.get('prompt', '')).strip()
            if not prompt:
                raise ValueError('payload.prompt is required')
            client, cfg = self._ollama()
            if payload.get('model'):
                client.model = str(payload['model'])
            system = str(payload.get('system') or (
                'You are an Apollo worker node. Complete only the assigned subtask. '
                'Return concise work product, assumptions, risks and verification notes.'
            ))
            response = client.chat_once([
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': prompt},
            ])
            message = response.get('message', {}) if isinstance(response, dict) else {}
            return {
                'model': response.get('model', client.model) if isinstance(response, dict) else client.model,
                'content': str(message.get('content', '')),
            }
        raise ValueError(kind)

    def _run_task(self, task_id):
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.get('status') == 'cancelled':
                return
            task['status'] = 'running'
            task['started_at'] = _utc_now()
            self._save_tasks()
        try:
            if task_id in self._cancelled:
                raise RuntimeError('task cancelled before execution')
            result = self._execute_task(task)
            status = 'completed'
            error = None
        except Exception as exc:
            result = None
            status = 'cancelled' if task_id in self._cancelled else 'failed'
            error = f'{type(exc).__name__}: {exc}'
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task['status'] = status
                task['finished_at'] = _utc_now()
                task['result'] = result
                task['error'] = error
                task['evidence'] = {
                    'worker_device_id': self.config().get('device_id'),
                    'worker_device_name': self.config().get('device_name'),
                    'completed_at': task['finished_at'],
                }
                self._save_tasks()
            self._cancelled.discard(task_id)

    def start(self, host=None, port=None):
        if self._server is not None:
            return {'ok': True, 'already_running': True, 'status': self.status()}
        cfg = self.config()
        host = str(host if host is not None else cfg.get('host', '0.0.0.0'))
        port = int(port if port is not None else cfg.get('port', 8766))
        service = self

        class Handler(BaseHTTPRequestHandler):
            server_version = 'ApolloDeviceAgent/1.0'
            def log_message(self, fmt, *args):
                return
            def _send(self, code, payload):
                data = json.dumps(payload, default=str).encode('utf-8')
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def _body(self):
                length = int(self.headers.get('Content-Length', '0') or 0)
                if length > 4 * 1024 * 1024:
                    raise ValueError('request too large')
                return self.rfile.read(length) if length else b''
            def _auth(self, body=b''):
                ok, detail = service.verify_request(self.command, urlparse(self.path).path, self.headers, body)
                if not ok:
                    self._send(401, {'ok': False, 'error': detail})
                    return False
                return True
            def do_GET(self):
                path = urlparse(self.path).path
                if path == '/identity':
                    self._send(200, {'ok': True, 'identity': service.identity()})
                    return
                if not self._auth():
                    return
                if path == '/status':
                    self._send(200, {'ok': True, 'status': service.status()})
                    return
                if path.startswith('/task/'):
                    task = service.task_status(path.split('/', 2)[-1])
                    self._send(200 if task else 404, {'ok': bool(task), 'task': task, 'error': None if task else 'task not found'})
                    return
                self._send(404, {'ok': False, 'error': 'not found'})
            def do_POST(self):
                path = urlparse(self.path).path
                try:
                    body = self._body()
                except Exception as exc:
                    self._send(400, {'ok': False, 'error': str(exc)})
                    return
                if not self._auth(body):
                    return
                try:
                    payload = json.loads(body.decode('utf-8')) if body else {}
                    if path == '/task':
                        self._send(202, service.submit_task(payload))
                        return
                    if path.startswith('/task/') and path.endswith('/cancel'):
                        self._send(200, service.cancel_task(path.split('/')[2]))
                        return
                    self._send(404, {'ok': False, 'error': 'not found'})
                except Exception as exc:
                    self._send(400, {'ok': False, 'error': f'{type(exc).__name__}: {exc}'})

        try:
            self._server = ThreadingHTTPServer((host, port), Handler)
        except OSError as exc:
            self._server = None
            return {'ok': False, 'error': f'{type(exc).__name__}: {exc}'}
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True, name='apollo-device-agent')
        self._thread.start()
        return {'ok': True, 'status': self.status()}

    def stop(self):
        if self._server is None:
            return {'ok': True, 'already_stopped': True}
        server = self._server
        self._server = None
        try:
            server.shutdown()
            server.server_close()
        finally:
            self._thread = None
        return {'ok': True, 'stopped': True}
