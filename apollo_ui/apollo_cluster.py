from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import json
import time
import uuid

from apollo_fleet import FleetAuthority
from apollo_storage import StorageLayout


def _now():
    return datetime.now(timezone.utc).isoformat()


class ClusterCoordinator:
    def __init__(self, base_dir):
        self.base = Path(base_dir).resolve()
        self.storage = StorageLayout(self.base)
        self.storage.ensure_layout()
        self.fleet = FleetAuthority(self.base)
        self.log_dir = self.storage.reports / 'cluster'
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def workers(self, refresh=True):
        devices = self.fleet.refresh_all() if refresh else self.fleet.devices()
        return [d for d in devices if d.get('online') and str(d.get('role', 'worker')).lower() in {'worker', 'hybrid', 'coordinator'}]

    @staticmethod
    def _eligible(device, task):
        required = set(task.get('requires') or [])
        caps = set((device.get('status') or {}).get('capabilities') or [])
        return required.issubset(caps)

    def plan(self, tasks, refresh=True):
        workers = self.workers(refresh=refresh)
        if not workers:
            return {'ok': False, 'error': 'No online Apollo workers are enrolled.', 'assignments': []}
        load = {w['device_id']: 0 for w in workers}
        assignments = []
        for raw in tasks:
            task = dict(raw or {})
            task.setdefault('task_id', str(uuid.uuid4()))
            candidates = [w for w in workers if self._eligible(w, task)]
            if not candidates:
                assignments.append({'task': task, 'device': None, 'error': 'No worker satisfies requirements.'})
                continue
            candidates.sort(key=lambda w: (load[w['device_id']], str(w.get('name', ''))))
            chosen = candidates[0]
            load[chosen['device_id']] += 1
            assignments.append({'task': task, 'device': chosen, 'error': None})
        return {'ok': True, 'workers': workers, 'assignments': assignments}

    def _wait(self, device_id, task_id, timeout):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            try:
                last = self.fleet.task_status(device_id, task_id)
            except Exception as exc:
                last = {'task_id': task_id, 'status': 'communication_error', 'error': f'{type(exc).__name__}: {exc}'}
                time.sleep(1)
                continue
            if last and last.get('status') in {'completed', 'failed', 'cancelled'}:
                return last
            time.sleep(0.4)
        return {'task_id': task_id, 'status': 'lease_expired', 'error': f'task did not finish within {timeout}s', 'last_known': last}

    def _execute(self, job_id, assignment, timeout):
        task = assignment['task']
        device = assignment.get('device')
        if not device:
            return {'task_id': task.get('task_id'), 'status': 'unscheduled', 'error': assignment.get('error')}
        envelope = {
            'job_id': job_id,
            'task_id': task.get('task_id'),
            'type': task.get('type', 'ollama_prompt'),
            'objective': task.get('objective', ''),
            'payload': task.get('payload') or {},
            'lease_seconds': min(max(int(timeout), 30), 3600),
        }
        try:
            accepted = self.fleet.send_task(device['device_id'], envelope)
            remote_id = accepted.get('task_id')
            result = self._wait(device['device_id'], remote_id, timeout)
            return {
                'task_id': task.get('task_id'),
                'objective': task.get('objective', ''),
                'worker': {'device_id': device.get('device_id'), 'name': device.get('name')},
                'status': result.get('status'),
                'result': result.get('result'),
                'error': result.get('error'),
                'evidence': result.get('evidence'),
            }
        except Exception as exc:
            return {
                'task_id': task.get('task_id'),
                'objective': task.get('objective', ''),
                'worker': {'device_id': device.get('device_id'), 'name': device.get('name')},
                'status': 'communication_error',
                'error': f'{type(exc).__name__}: {exc}',
            }

    def run_tasks(self, tasks, timeout_per_task=600, job_id=None):
        if not isinstance(tasks, list) or not tasks:
            raise ValueError('tasks must be a non-empty list')
        job_id = str(job_id or uuid.uuid4())
        prepared = []
        for i, raw in enumerate(tasks):
            task = dict(raw or {})
            task.setdefault('task_id', f'{job_id}-{i+1}')
            task.setdefault('type', 'ollama_prompt')
            task.setdefault('objective', f'Subtask {i+1}')
            if task['type'] == 'ollama_prompt':
                task.setdefault('requires', ['ollama_prompt'])
            prepared.append(task)
        plan = self.plan(prepared, refresh=True)
        if not plan.get('ok'):
            return {'ok': False, 'job_id': job_id, 'error': plan.get('error'), 'results': []}
        results = []
        with ThreadPoolExecutor(max_workers=max(1, min(16, len(plan['assignments'])))) as pool:
            futures = [pool.submit(self._execute, job_id, a, int(timeout_per_task)) for a in plan['assignments']]
            for future in as_completed(futures):
                results.append(future.result())
        counts = {}
        for item in results:
            state = str(item.get('status', 'unknown'))
            counts[state] = counts.get(state, 0) + 1
        record = {'job_id': job_id, 'created_at': _now(), 'task_count': len(prepared), 'status_counts': counts, 'results': results}
        target = self.log_dir / f'{job_id}.json'
        target.write_text(json.dumps(record, indent=2, default=str) + '\n', encoding='utf-8')
        return {'ok': all(r.get('status') == 'completed' for r in results), **record, 'report_path': str(target)}

    def parallel_prompts(self, subtasks, shared_context='', timeout_per_task=600):
        if not isinstance(subtasks, list) or not subtasks:
            raise ValueError('subtasks must be a non-empty list')
        tasks = []
        for item in subtasks:
            objective = str(item).strip()
            if not objective:
                continue
            prompt = objective
            if str(shared_context).strip():
                prompt = f'Shared project context:\n{shared_context}\n\nAssigned subtask:\n{objective}'
            tasks.append({
                'type': 'ollama_prompt',
                'objective': objective,
                'requires': ['ollama_prompt'],
                'payload': {'prompt': prompt},
            })
        return self.run_tasks(tasks, timeout_per_task=timeout_per_task)
