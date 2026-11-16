"""Network/model fakes exercise orchestration, not foreign code on the host."""
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from apollo_source_learning import SourceLearning, GitHubSource, YieldWork, validate_analysis

SOURCE = {'repo': 'example/retrieval', 'commit': 'a'*40, 'licence': 'MIT',
          'url': 'https://github.com/example/retrieval/tree/'+'a'*40,
          'files': {'LICENSE': 'MIT fixture', 'sample.py': 'def lookup(x): return x'},
          'scope': 'small test sample'}
PLAN = {'title': 'Local AI setup audit', 'offer': 'A small setup audit, subject to owner skill verification',
        'deliverables': 'Configuration report and documented checks', 'risks': 'No customers or income verified',
        'validation': 'Owner verifies delivery ability and tests demand before any offer is published'}
ANALYSIS = {'lesson': 'Try a bounded lookup cache', 'limitations': 'Not benchmarked on Apollo',
            'experiment': 'Compare identical lookup results', 'files': {}, 'funding': PLAN}
COMPARISON = {**ANALYSIS, 'files': {
    'baseline.py': 'def lookup(items, key):\n return next((v for k,v in items if k==key), None)\n',
    'candidate.py': 'def lookup(items, key):\n return dict(items).get(key)\n',
    'tests/test_candidate.py': 'import unittest\nimport baseline, candidate\nclass Compare(unittest.TestCase):\n def test_same_cases(self):\n  for key in ("a", "b", "missing"):\n   self.assertEqual(baseline.lookup([("a",1),("b",2)],key),candidate.lookup([("a",1),("b",2)],key))\n'}}


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1800000000.
        self.idle = True
        self.service = SourceLearning(self.temp.name, idle=lambda: self.idle, clock=lambda: self.now)
        self.addCleanup(self.service.close)
        self.api = patch('apollo_source_learning.GitHubSource').start()
        self.addCleanup(patch.stopall)
        self.api.return_value.discover.return_value = [SOURCE['repo']]
        self.api.return_value.study.return_value = SOURCE
        self.service.analyse = lambda source: ANALYSIS

    def pulse(self):
        with patch('psutil.virtual_memory') as memory, patch('psutil.cpu_percent', return_value=0):
            memory.return_value.available = 8*1024**3
            return self.service.pulse()

    def test_standing_work_starts_without_fresh_prompt_and_saves_provenance(self):
        result = self.pulse()
        self.assertEqual(result['state'], 'recorded')
        saved = self.service.status()['studies'][0]
        self.assertEqual(saved['source']['commit'], 'a'*40)
        self.assertEqual(saved['receipt']['status'], 'not_attempted')
        self.assertEqual(saved['analysis']['limitations'], 'Not benchmarked on Apollo')
        self.assertEqual(len(self.service.status()['funding']), 1)
        self.assertNotIn('files', saved['source'])

    def test_daily_and_hourly_budget_persist_and_cross_instance_lease(self):
        other = SourceLearning(self.temp.name, idle=lambda: True, clock=lambda: self.now)
        self.addCleanup(other.close)
        self.assertTrue(self.service.reserve())
        self.assertFalse(other.reserve())
        for _ in range(3):
            self.now += 3601
            self.assertTrue(other.reserve())
        self.now += 3601
        self.assertFalse(self.service.reserve())
        self.now += 86400
        self.assertTrue(self.service.reserve())

    def test_pause_stop_survive_restart_and_busy_does_no_network(self):
        self.idle = False
        self.assertTrue(self.pulse()['waiting'])
        self.api.assert_not_called()
        self.idle = True
        self.service.control('stop')
        other = SourceLearning(self.temp.name, idle=lambda: True, clock=lambda: self.now)
        try:
            self.assertEqual(other.status()['mode'], 'stopped')
            self.assertTrue(other.pulse()['waiting'])
        finally:
            other.close()
        self.service.control('resume')
        self.assertEqual(self.pulse()['state'], 'recorded')

    def test_resource_gate_prevents_model_and_network(self):
        with patch('psutil.virtual_memory') as memory:
            memory.return_value.available = 1
            self.assertTrue(self.service.pulse()['waiting'])
        self.api.assert_not_called()

    def test_one_button_queues_public_research_and_records_evidence_then_proposes_pilot(self):
        from apollo_learning_missions import MissionService
        counter = [0]
        def collect(query, filename, limit):
            counter[0] += 1
            return {'source_pages_fetched': 1,
                    'sources': [{'url': 'https://market.example/evidence/'+str(counter[0])}],
                    'saved': {'saved': True, 'filename': filename}}
        missions = MissionService(self.temp.name, memory=True, auto_thread=False, executor=collect)
        self.addCleanup(missions.store.close)
        self.addCleanup(missions.shutdown)
        self.service.missions = lambda: missions
        self.service.evidence_reader = lambda filename: 'Fixture market evidence. Customer demand still needs a paid pilot.'
        result = self.service.start_upgrade_plan()
        self.assertTrue(Path(result['file']).exists())
        self.service.funding_tick()
        self.service.start_upgrade_plan()
        self.service.funding_tick()
        self.assertEqual(len(missions.store.list()), 1)
        mid = int(self.service.state('funding_mission_id'))
        self.service.control('pause')
        self.assertEqual(missions.store.status(mid)['state'], 'PAUSED')
        self.service.control('resume')
        with patch('apollo_idle_learning.idle_ready', return_value=True), patch('apollo_idle_learning.foreground_busy', return_value=False):
            for _ in range(3):
                with missions.store.lock, missions.store.db:
                    missions.store.db.execute('UPDATE missions SET next_due=0 WHERE id=?', (mid,))
                missions.tick()
        self.assertEqual(missions.store.status(mid)['state'], 'COMPLETED')
        self.assertTrue(self.pulse()['funding_review_ready'])
        self.service.write_plan()
        plan = Path(result['file']).read_text()
        self.assertIn('market.example/evidence/', plan)
        self.assertIn('No earnings are claimed', plan)
        self.assertEqual(self.service.status()['funding'][0]['state'], 'proposed')
        self.api.assert_not_called()

    def test_upgrade_case_needs_repeated_measured_pressure_and_does_not_claim_pc_required(self):
        for _ in range(2):
            self.service.resource_sample(1, 20, True)
            self.now += 16
        self.assertEqual(self.service.status()['upgrade_case'], {})
        self.service.resource_sample(1, 20, True)
        case = self.service.status()['upgrade_case']
        self.assertEqual(len(case['evidence']), 3)
        self.assertIn('does not establish', case['limits'])
        self.assertIn('no verified earnings', case['funding'])

    def test_seen_repository_is_not_repeated(self):
        self.pulse()
        self.now += 3601
        self.assertTrue(self.pulse()['waiting'])
        self.assertEqual(self.api.return_value.study.call_count, 1)

    def test_interrupted_sample_resumes_without_refetch(self):
        self.service.analyse = lambda source: (_ for _ in ()).throw(YieldWork('User returned'))
        self.assertIn('yielded', self.pulse())
        self.assertEqual(self.service.status()['studies'][0]['state'], 'sampled')
        self.service.analyse = lambda source: ANALYSIS
        self.now += 3601
        self.assertEqual(self.pulse()['state'], 'recorded')
        self.assertEqual(self.api.return_value.study.call_count, 1)

    def test_unavailable_docker_preserves_comparison_and_allows_other_discovery(self):
        self.service.analyse = lambda source: COMPARISON
        with patch('apollo_foundry_sandbox.run_sandbox', return_value={'status': 'unavailable'}):
            self.assertEqual(self.pulse()['state'], 'awaiting_sandbox')
        self.now += 3601
        self.api.return_value.discover.return_value = ['other/project']
        self.api.return_value.study.return_value = {**SOURCE, 'repo': 'other/project'}
        with patch('apollo_foundry_sandbox.availability', return_value={'ok': False}), patch('apollo_foundry_sandbox.run_sandbox', return_value={'status': 'unavailable'}):
            self.pulse()
        self.assertEqual(len(self.service.status()['studies']), 2)
        self.now += 3601
        with patch('apollo_foundry_sandbox.availability', return_value={'ok': True}), patch('apollo_foundry_sandbox.run_sandbox', return_value={'status': 'passed'}):
            self.assertEqual(self.pulse()['state'], 'review')

    def test_three_invalid_model_attempts_block_without_claimed_improvement(self):
        self.service.analyse = lambda source: {'lesson': 'missing fields'}
        for _ in range(3):
            self.assertIn('error', self.pulse())
            self.now += 3601
        self.assertEqual(self.service.status()['studies'][0]['state'], 'blocked')

    def test_funding_needs_owner_approval_and_only_prepares_local_drafts(self):
        self.pulse()
        self.assertFalse(self.service.prepare_approved_funding())
        proposal = self.service.status()['funding'][0]
        self.service.owner_funding_control(proposal['id'], 'approve_local')
        self.service.control('pause')
        self.assertFalse(self.service.prepare_approved_funding())
        self.service.control('resume')
        self.assertTrue(self.pulse()['funding_prepared'])
        prepared = self.service.status()['funding'][0]
        self.assertEqual(prepared['state'], 'prepared')
        self.assertFalse(prepared['receipt']['external_actions'])
        self.assertFalse(prepared['receipt']['revenue_verified'])
        self.assertEqual(prepared['receipt']['spend_gbp'], 0)
        self.assertTrue((Path(prepared['receipt']['folder'])/'offer_draft.txt').exists())
        with self.assertRaises(ValueError):
            self.service.owner_funding_control(proposal['id'], 'publish')

    def test_validation_accepts_no_paths_or_install_commands_as_actions(self):
        for key in ('../../main.py', '/tmp/escape.py', 'install.bat'):
            with self.assertRaises(ValueError):
                validate_analysis({**ANALYSIS, 'files': {key: 'print(1)'}})
        with self.assertRaises(SyntaxError):
            validate_analysis({**COMPARISON, 'files': {**COMPARISON['files'], 'candidate.py': 'def ('}})
        with self.assertRaises(ValueError):
            validate_analysis({**ANALYSIS, 'funding': {'spend': 100}})

    def test_sandbox_snapshot_retains_source_and_does_not_execute_on_host(self):
        self.service.deadline = self.now+120
        def sandbox(folder, kind, **kwargs):
            self.assertEqual(kind, 'unit')
            self.assertIn('MIT fixture', (Path(folder)/'SOURCE.txt').read_text())
            self.assertIn('baseline', (Path(folder)/'tests/test_candidate.py').read_text())
            self.assertIn('cancelled', kwargs)
            return {'status': 'passed'}
        with patch('apollo_foundry_sandbox.run_sandbox', side_effect=sandbox):
            result = self.service.experiment(SOURCE, COMPARISON)
        self.assertFalse(result['applied'])
        self.assertIn('unverified', result['interpretation'])


class ApiTests(unittest.TestCase):
    def test_pinned_blobs_integrity_and_licence_retention(self):
        api = GitHubSource()
        licence = b'MIT licence fixture'
        code = b'def lookup(x): return x'
        def blob(data):
            return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        rows = [{'path': name, 'mode': '100644', 'type': 'blob', 'size': len(data), 'sha': blob(data)}
                for name, data in [('LICENSE', licence), ('src/lookup.py', code)]]
        values = iter([{'license': {'spdx_id': 'MIT'}, 'default_branch': 'main'},
                       {'sha': 'a'*40}, {'tree': rows},
                       {'encoding': 'base64', 'content': base64.b64encode(licence).decode()},
                       {'encoding': 'base64', 'content': base64.b64encode(code).decode()}])
        paths = []
        api.get = lambda path: (paths.append(path), next(values))[1]
        source = api.study('example/project')
        self.assertIn('LICENSE', source['files'])
        self.assertIn('/git/trees/'+'a'*40, paths[2])
        self.assertEqual(source['commit'], 'a'*40)

    def test_missing_or_unsupported_licence_refuses_port(self):
        api = GitHubSource()
        api.get = lambda path: {'license': {'spdx_id': 'NOASSERTION'}}
        with self.assertRaises(PermissionError):
            api.study('example/project')
        with self.assertRaises(ValueError):
            api.study('../../outside')

    def test_no_redirects_private_urls_or_arbitrary_endpoints(self):
        from apollo_source_learning import NoRedirect
        api = GitHubSource()
        for path in ('https://localhost/private', '/user', '/repos/../secret'):
            with self.assertRaises(ValueError):
                api.get(path)
        with self.assertRaises(PermissionError):
            NoRedirect().redirect_request(None, None, 302, '', {}, 'http://localhost')


@unittest.skipUnless(os.environ.get('APOLLO_FOUNDRY_INTEGRATION') == '1', 'Real Docker runs in isolated CI')
class DockerTests(unittest.TestCase):
    def test_comparison_really_runs_in_container(self):
        with tempfile.TemporaryDirectory() as temp:
            service = SourceLearning(temp, validation=True, idle=lambda: True)
            try:
                service.deadline = service.clock()+120
                receipt = service.experiment(SOURCE, COMPARISON)
                self.assertEqual(receipt['status'], 'passed', receipt)
                self.assertTrue(receipt['executed_project_code'])
                self.assertIn('Ran 1 test', receipt['output'])
            finally:
                service.close()




@unittest.skipUnless(__import__('importlib.util', fromlist=['find_spec']).find_spec('PySide6'), 'Qt optional on headless checks')
class UiTests(unittest.TestCase):
    def test_owner_widgets_pause_review_and_approve_only_local_preparation(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication, QPushButton, QListWidget, QPlainTextEdit
        from apollo_source_learning_ui import source_learning_view
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temp:
            service = SourceLearning(temp, validation=True, idle=lambda: True)
            try:
                service.save_funding(1, PLAN)
                page = source_learning_view(service)
                page.findChild(QPushButton, 'self_upgrade_plan').click()
                self.assertTrue(Path(service.status()['plan_file']).exists())
                page.findChild(QPushButton, 'source_learning_pause').click()
                self.assertEqual(service.status()['mode'], 'paused')
                page.findChild(QPushButton, 'source_learning_resume').click()
                self.assertEqual(service.status()['mode'], 'active')
                page.findChild(QListWidget, 'source_funding_list').setCurrentRow(0)
                self.assertIn('validation', page.findChild(QPlainTextEdit, 'source_funding_detail').toPlainText())
                page.findChild(QPushButton, 'source_funding_approve_local').click()
                grant = service.status()['funding'][0]['grant']
                self.assertEqual(grant['max_spend_gbp'], 0)
                self.assertFalse(grant['external_actions'])
                page.findChild(QPushButton, 'source_learning_stop').click()
                self.assertEqual(service.status()['mode'], 'stopped')
                page.close()
                page.deleteLater()
                app.processEvents()
            finally:
                service.close()


class BoundaryTests(unittest.TestCase):
    def test_model_tools_cannot_approve_funding_or_resume_background_work(self):
        from modules.self_improvement_lab.module import Module
        with tempfile.TemporaryDirectory() as temp:
            module = Module({'base_dir': temp, 'validation': True})
            try:
                self.assertIsNone(module.source_learning.worker)
                self.assertIn('source_learning_status', [t['name'] for t in module.tools()])
                for action in ('owner_funding_control', 'resume', 'publish', 'approve_local'):
                    with self.assertRaises(KeyError):
                        module.run(action, {})
            finally:
                module.close()

    def test_foreign_source_cannot_move_analysis_to_external_model(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp)/'config.json').write_text(json.dumps({'ollama_url': 'https://outside.example', 'model': 'local'}))
            service = SourceLearning(temp, validation=True, idle=lambda: True)
            try:
                with self.assertRaises(PermissionError):
                    service.analyse(SOURCE)
            finally:
                service.close()

    def test_cancelling_running_container_forces_cleanup(self):
        from apollo_foundry_sandbox import _execute_bounded
        class Running:
            returncode = None
            def poll(self): return self.returncode
            def kill(self): self.returncode = -9
            def wait(self, timeout=None): return self.returncode
        with patch('apollo_foundry_sandbox.subprocess.Popen', return_value=Running()), patch('apollo_foundry_sandbox._force_remove', return_value=True) as remove:
            receipt = _execute_bounded(['docker', 'run'], 'docker', 'apollo-foundry-cancel', 30, cancelled=lambda: True)
        self.assertTrue(receipt['interrupted'])
        self.assertTrue(receipt['cleanup_ok'])
        remove.assert_called_once_with('docker', 'apollo-foundry-cancel')


if __name__ == '__main__':
    unittest.main()
