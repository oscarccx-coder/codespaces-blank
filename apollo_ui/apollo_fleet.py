from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import threading
import urllib.parse
import urllib.request
import uuid

from apollo_device_agent import sign_request
from apollo_storage import StorageLayout


def _now():
    return datetime.now(timezone.utc).isoformat()


def _write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


class FleetAuthority:
    def __init__(self, base_dir):
        self.base = Path(base_dir).resolve()
        self.storage = StorageLayout(self.base)
        self.storage.ensure_layout()
        self.state_dir = self.storage.state / 'fleet'
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.state_dir / 'registry.json'
        self._lock = threading.RLock()
        if not self.registry_path.exists():
            _write(self.registry_path, {'schema_version': 1, 'authority_id': str(uuid.uuid4()), 'devices': {}})

    def _load(self):
        try:
            data = json.loads(self.registry_path.read_text(encoding='utf-8'))
        except Exception:
            data = {'schema_version': 1, 'authority_id': str(uuid.uuid4()), 'devices': {}}
        if not isinstance(data.get('devices'), dict):
            data['devices'] = {}
        return data

    def _save(self, data):
        _write(self.registry_path, data)

    @staticmethod
    def _base_url(value):
        value = str(value or '').strip().rstrip('/')
        if not value:
            raise ValueError('device URL is required')
        if not value.startswith(('http://', 'https://')):
            value = 'http://' + value
        parsed = urllib.parse.urlparse(value)
        if not parsed.hostname:
            raise ValueError('invalid device URL')
        return value

    @staticmethod
    def _request_json(url, method='GET', payload=None, token=None, timeout=4):
        body = b'' if payload is None else json.dumps(payload).encode('utf-8')
        parsed = urllib.parse.urlparse(url)
        path = parsed.path or '/'
        headers = {'Content-Type': 'application/json'}
        if token:
            headers.update(sign_request(token, method, path, body))
        request = urllib.request.Request(url, data=body if method != 'GET' else None, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))

    @staticmethod
    def public_record(record):
        out = dict(record)
        out.pop('token', None)
        return out

    def enroll(self, url, token, name=None, role='worker', group='Default'):
        base_url = self._base_url(url)
        token = str(token or '').strip()
        if not token:
            raise ValueError('enrollment token is required')
        identity = (self._request_json(base_url + '/identity').get('identity') or {})
        device_id = str(identity.get('device_id', '')).strip()
        if not device_id:
            raise ValueError('device returned no device_id')
        status = (self._request_json(base_url + '/status', token=token).get('status') or {})
        record = {
            'device_id': device_id,
            'name': str(name or identity.get('device_name') or device_id),
            'url': base_url,
            'token': token,
            'role': str(role or identity.get('role') or 'worker'),
            'group': str(group or identity.get('group') or 'Default'),
            'enrolled_at': _now(),
            'last_seen': _now(),
            'online': True,
            'status': status,
            'revoked': False,
        }
        with self._lock:
            data = self._load()
            data['devices'][device_id] = record
            self._save(data)
        return self.public_record(record)

    def devices(self, include_revoked=False):
        with self._lock:
            data = self._load()
        out = []
        for record in data['devices'].values():
            if record.get('revoked') and not include_revoked:
                continue
            out.append(self.public_record(record))
        return sorted(out, key=lambda r: (str(r.get('group', '')), str(r.get('name', ''))))

    def _private(self, device_id):
        with self._lock:
            record = self._load()['devices'].get(str(device_id))
        if not record:
            raise KeyError(f'Unknown fleet device: {device_id}')
        if record.get('revoked'):
            raise PermissionError('Device is revoked')
        return record

    def refresh_device(self, device_id):
        record = self._private(device_id)
        try:
            status = (self._request_json(record['url'] + '/status', token=record['token']).get('status') or {})
            online = True
            error = None
        except Exception as exc:
            status = record.get('status') or {}
            online = False
            error = f'{type(exc).__name__}: {exc}'
        with self._lock:
            data = self._load()
            current = data['devices'].get(str(device_id), record)
            current['online'] = online
            current['last_check'] = _now()
            if online:
                current['last_seen'] = _now()
                current['status'] = status
                current.pop('last_error', None)
            else:
                current['last_error'] = error
            data['devices'][str(device_id)] = current
            self._save(data)
        return self.public_record(current)

    def refresh_all(self):
        devices = self.devices()
        if not devices:
            return []
        results = []
        with ThreadPoolExecutor(max_workers=min(16, len(devices))) as pool:
            futures = {pool.submit(self.refresh_device, d['device_id']): d['device_id'] for d in devices}
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as exc:
                    results.append({'device_id': futures[future], 'online': False, 'last_error': f'{type(exc).__name__}: {exc}'})
        return results

    def update_metadata(self, device_id, name=None, role=None, group=None):
        with self._lock:
            data = self._load()
            record = data['devices'].get(str(device_id))
            if not record:
                raise KeyError(device_id)
            if name is not None and str(name).strip():
                record['name'] = str(name).strip()
            if role is not None and str(role).strip():
                record['role'] = str(role).strip()
            if group is not None and str(group).strip():
                record['group'] = str(group).strip()
            self._save(data)
            return self.public_record(record)

    def revoke(self, device_id):
        with self._lock:
            data = self._load()
            record = data['devices'].get(str(device_id))
            if not record:
                raise KeyError(device_id)
            record['revoked'] = True
            record['online'] = False
            record['revoked_at'] = _now()
            self._save(data)
        return {'ok': True, 'device_id': str(device_id), 'revoked': True}

    def remove(self, device_id):
        with self._lock:
            data = self._load()
            existed = data['devices'].pop(str(device_id), None) is not None
            self._save(data)
        return {'ok': existed, 'device_id': str(device_id), 'removed': existed}

    def send_task(self, device_id, envelope):
        record = self._private(device_id)
        return self._request_json(record['url'] + '/task', method='POST', payload=envelope, token=record['token'], timeout=5)

    def task_status(self, device_id, task_id):
        record = self._private(device_id)
        response = self._request_json(record['url'] + f'/task/{task_id}', token=record['token'], timeout=5)
        return response.get('task')

    def cancel_task(self, device_id, task_id):
        record = self._private(device_id)
        return self._request_json(record['url'] + f'/task/{task_id}/cancel', method='POST', payload={}, token=record['token'], timeout=5)
