from pathlib import Path
import json
import tempfile
import shutil
import time

from apollo_device_agent import DeviceAgentService
from apollo_fleet import FleetAuthority
from apollo_cluster import ClusterCoordinator

root = Path(tempfile.mkdtemp(prefix='apollo_cluster_test_'))
try:
    (root / 'config.json').write_text(json.dumps({
        'version': '7.5.12.4',
        'ollama_url': 'http://127.0.0.1:65534',
        'model': 'none',
        'temperature': 0.1,
        'num_ctx': 2048
    }), encoding='utf-8')
    (root / 'workspace').mkdir()
    (root / 'workspace' / 'sample.txt').write_text('apollo cluster', encoding='utf-8')

    agent = DeviceAgentService(root)
    agent.configure(host='127.0.0.1', port=0, device_name='Test Worker', role='worker', group='Tests')
    started = agent.start()
    assert started['ok'], started
    url = f"http://127.0.0.1:{agent.actual_port()}"

    fleet = FleetAuthority(root)
    enrolled = fleet.enroll(url, agent.enrollment_token(), name='Test Worker', group='Tests')
    assert enrolled['online'] is True

    # Wrong token cannot authenticate.
    failed = False
    try:
        FleetAuthority(root)._request_json(url + '/status', token='wrong-token', timeout=2)
    except Exception:
        failed = True
    assert failed

    accepted = fleet.send_task(enrolled['device_id'], {
        'type': 'python_syntax',
        'objective': 'validate tiny snippet',
        'payload': {'code': 'x = 1 + 2\n'},
        'lease_seconds': 30,
    })
    task_id = accepted['task_id']
    deadline = time.time() + 10
    result = None
    while time.time() < deadline:
        result = fleet.task_status(enrolled['device_id'], task_id)
        if result and result.get('status') in {'completed','failed','cancelled'}:
            break
        time.sleep(0.1)
    assert result['status'] == 'completed', result
    assert result['result']['valid'] is True

    cluster = ClusterCoordinator(root)
    run = cluster.run_tasks([
        {'type':'ping','objective':'node ping','requires':['ping'],'payload':{'n':1}},
        {'type':'sha256_text','objective':'hash test','requires':['sha256_text'],'payload':{'text':'Apollo'}},
        {'type':'workspace_file_hash','objective':'file hash','requires':['workspace_file_hash'],'payload':{'path':'sample.txt'}},
    ], timeout_per_task=20)
    assert run['ok'], run
    assert run['status_counts'].get('completed') == 3
    assert Path(run['report_path']).exists()

    agent.stop()
    offline = fleet.refresh_device(enrolled['device_id'])
    assert offline['online'] is False

    print('Fleet/Cluster network tests passed.')
finally:
    try:
        agent.stop()
    except Exception:
        pass
    shutil.rmtree(root, ignore_errors=True)
