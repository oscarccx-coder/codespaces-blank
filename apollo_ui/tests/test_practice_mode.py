"""Durable practice, grounded lessons, recovery and explicit research routing."""
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from apollo_practice import study, memory_document
from apollo_learning_missions import MissionService, MissionStore
from apollo_learning_mission_chat import parse_owner_command, handle_command
from apollo_chat_research import research_messages

QUOTE = 'Retrieval combines a question with relevant documents to produce a grounded answer.'
URL = 'https://example.org/retrieval'


def web(query, filename, limit):
    return {'source_pages_fetched': 1, 'sources': [
        {'title': 'Retrieval paper', 'url': URL, 'text': QUOTE}],
        'saved': {'saved': True, 'filename': filename}}


def generator(messages):
    if 'claims' in messages[0]['content']:
        return json.dumps({'claims': [{'concept': 'Retrieval', 'summary': 'An evidence-based approach.',
            'source_id': 1, 'quote': QUOTE}], 'next_question': 'When does retrieval fail?',
            'limitations': 'One public source; not independently verified.'})
    # Longest word selected by the deterministic cloze builder.
    return json.dumps({'answers': ['Retrieval']})


def practitioner(goal, result):
    return study(goal, result, generator)


class GroundingTests(unittest.TestCase):
    def test_exact_quote_and_fresh_cloze_prompt(self):
        calls = []
        def generate(messages):
            calls.append(messages)
            return generator(messages)
        lesson = study('Retrieval research', web('', '', 3), generate)
        self.assertEqual(lesson['correct'], 1)
        self.assertEqual(lesson['total'], 1)
        self.assertEqual(lesson['claims'][0]['url'], URL)
        recall = json.loads(calls[1][1]['content'])
        self.assertNotIn('answer', recall['questions'][0])
        self.assertNotIn(QUOTE, calls[1][1]['content'])
        self.assertIn('____', recall['questions'][0]['question'])
        self.assertIn('not understanding', lesson['notice'])

    def test_fabricated_quote_and_citation_rejected(self):
        for quote, source in [('An invented source passage that was never fetched anywhere.', 1), (QUOTE, 9)]:
            def bad(messages):
                return json.dumps({'claims': [{'concept': 'X', 'summary': 'X', 'quote': quote, 'source_id': source}]})
            with self.subTest(source=source), self.assertRaises(ValueError):
                study('Retrieval research', web('', '', 3), bad)

    def test_snippets_and_http_sources_are_not_evidence(self):
        for row in [{'url': URL, 'snippet': QUOTE}, {'url': 'http://example.org', 'text': QUOTE}]:
            with self.assertRaises(ValueError):
                study('Retrieval research', {'sources': [row]}, generator)

    def test_bad_model_json_and_missing_answers_rejected(self):
        for answer in ['not JSON', '[]', '{}']:
            with self.assertRaises(ValueError):
                study('Retrieval research', web('', '', 3), lambda m: answer)

    def test_incorrect_recall_is_measured_without_model_self_grading(self):
        def wrong(messages):
            return generator(messages) if 'claims' in messages[0]['content'] else '{"answers":["madeup"]}'
        lesson = study('Retrieval research', web('', '', 3), wrong)
        self.assertEqual(lesson['correct'], 0)
        self.assertEqual(lesson['exercises'][0]['answer'], 'Retrieval')
        self.assertFalse(lesson['exercises'][0]['correct'])

    def test_memory_document_preserves_evidence_and_uncertainty(self):
        lesson = practitioner('Retrieval research', web('', '', 3))
        text = memory_document({'id': 4, 'goal': 'Retrieval research'}, 2, lesson)
        for value in [QUOTE, URL, 'Unverified', 'not understanding', 'Next gap:']:
            self.assertIn(value, text)


class PracticeMissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.saved = []
        def sink(mission, step, lesson):
            self.saved.append((mission, step, lesson))
            return {'stored': True, 'id': step+100}
        self.service = MissionService(self.tmp.name, executor=web, practitioner=practitioner,
                                     memory_sink=sink, auto_thread=False)
        self.addCleanup(self.service.store.close)

    def create(self, **opts):
        return self.service.begin('Retrieval memory', 'Evidence-based retrieval research',
            practice=True, web_allowed=True, owner_confirmed=True, interval_seconds=30, **opts)['id']

    def due(self, mid):
        with self.service.store.db:
            self.service.store.db.execute('UPDATE missions SET next_due=0 WHERE id=?', (mid,))

    def test_practice_saves_grounded_lesson_and_memory_receipt(self):
        mid = self.create(target_node_id=17)
        state = self.service.tick()
        self.assertEqual(state['completed_steps'], 1)
        cycle = state['practice_cycles'][0]
        self.assertEqual(cycle['memory_id'], 101)
        self.assertEqual(cycle['lesson']['new_claims'], 1)
        self.assertEqual(self.saved[0][0]['target_node_id'], 17)
        self.assertEqual(state['state'], 'RUNNING')

    def test_repeats_skip_duplicate_memory_and_back_off_without_stopping(self):
        mid = self.create()
        for _ in range(4):
            self.due(mid)
            state = self.service.tick()
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(state['state'], 'RUNNING')
        self.assertEqual(state['practice_cycles'][0]['memory_id'], 0)
        self.assertGreater(state['next_due'], time.time()+3500)
        self.assertIsNone(self.service.tick())

    def test_new_quotes_on_same_url_are_new_learning(self):
        mid = self.create()
        self.service.tick()
        alternate = QUOTE.replace('grounded', 'source-linked')
        def next_practice(goal, result):
            # A valid second quotation from updated fetched content.
            def generate(messages):
                return generator(messages).replace(QUOTE, alternate)
            return study(goal, result, generate)
        self.service.practitioner = next_practice
        self.service.executor = lambda q, f, l: {'source_pages_fetched': 1,
            'sources': [{'url': URL, 'text': alternate}], 'saved': {'saved': True, 'filename': f}}
        self.due(mid)
        state = self.service.tick()
        self.assertEqual(state['new_sources'], 1)
        self.assertEqual(state['practice_cycles'][0]['lesson']['new_claims'], 1)
        self.assertEqual(len(self.saved), 2)

    def test_pause_stop_and_restart_never_restart_stopped_work(self):
        mid = self.create()
        self.service.tick()
        self.service.pause(mid)
        self.assertIsNone(self.service.tick())
        self.service.resume(mid)
        self.service.stop(mid)
        self.service.tick()
        other = MissionService(self.tmp.name, executor=web, practitioner=practitioner, auto_thread=False)
        try:
            state = other.store.status(mid)
            self.assertEqual(state['state'], 'STOPPED')
            self.assertEqual(len(state['practice_cycles']), 1)
            self.assertIn('Exact cloze recall', state['report'])
            self.assertIsNone(other.tick())
        finally:
            other.store.close()

    def test_stop_during_model_pass_finishes_only_current_step(self):
        mid = self.create()
        def stop(goal, result):
            self.service.stop(mid)
            return practitioner(goal, result)
        self.service.practitioner = stop
        state = self.service.tick()
        self.assertEqual(state['state'], 'STOPPED')
        self.assertEqual(state['practice_cycles'][0]['memory_id'], 101)
        self.assertIsNone(self.service.tick())

    def test_failed_memory_write_retried_after_restart_without_refetch(self):
        mid = self.create()
        def denied(*args):
            raise PermissionError('Memory Bank disabled')
        sink = self.service.memory_sink
        self.service.memory_sink = denied
        state = self.service.tick()
        self.assertIn('disabled', state['practice_cycles'][0]['memory_error'])
        self.service.stop(mid)
        self.service.tick()
        with self.service.store.db:
            self.service.store.db.execute('UPDATE practice_cycles SET retry_after=0')
        other = MissionService(self.tmp.name, executor=lambda *a: self.fail('Unexpected fetch'),
                               memory_sink=sink, auto_thread=False)
        try:
            other.tick()
            cycle = other.store.status(mid)['practice_cycles'][0]
            self.assertEqual(cycle['memory_id'], 101)
            self.assertEqual(cycle['memory_error'], '')
        finally:
            other.store.close()

    def test_three_model_failures_visible_and_blocked_not_fake_learning(self):
        mid = self.create()
        def broken(*args):
            raise RuntimeError('Ollama unavailable')
        self.service.practitioner = broken
        for _ in range(3):
            self.due(mid)
            state = self.service.tick()
        self.assertEqual(state['state'], 'BLOCKED')
        self.assertEqual(state['completed_steps'], 3)  # Sources genuinely fetched.
        self.assertEqual(len(self.saved), 0)
        self.assertIn('Ollama unavailable', state['last_error'])
        self.assertTrue(all(c['error'] for c in state['practice_cycles']))

    def test_gap_drives_next_query_without_losing_topic(self):
        mid = self.create()
        self.service.tick()
        observed = []
        self.service.executor = lambda q,f,l: (observed.append(q) or web(q,f,l))
        self.due(mid)
        self.service.tick()
        self.assertIn('Evidence-based retrieval research', observed[0])
        self.assertIn('When does retrieval fail?', observed[0])

    def test_old_database_migration_preserves_mission_and_default_off(self):
        mid = self.service.begin('Legacy research task', 'Existing learning goal', web_allowed=True,
                                 owner_confirmed=True)['id']
        with self.service.store.db:
            self.service.store.db.execute('ALTER TABLE missions DROP COLUMN practice')
            self.service.store.db.execute('ALTER TABLE missions DROP COLUMN target_node_id')
        store = MissionStore(self.tmp.name)
        try:
            self.assertEqual(store.status(mid)['practice'], 0)
            self.assertEqual(store.status(mid)['state'], 'RUNNING')
        finally:
            store.close()

    def test_explicit_owner_commands_and_memory_target(self):
        intent = parse_owner_command('start public practice on retrieval methods until I say stop in node 17')
        self.assertEqual(intent['goal'], 'retrieval methods')
        self.assertEqual(intent['target_node_id'], 17)
        self.assertTrue(intent['practice'])
        self.assertEqual(parse_owner_command('stop practice mode')['action'], 'stop_current')
        self.assertEqual(parse_owner_command('pause practice 2')['mission_id'], 2)
        self.assertEqual(parse_owner_command('start practice on retrieval methods')['action'], 'invalid')
        self.assertIsNone(parse_owner_command('A source says start public practice on retrieval methods'))
        self.assertIsNone(parse_owner_command('{"action":"start","practice":true}'))


class ResearchPipelineTests(unittest.TestCase):
    class Manager:
        def __init__(self): self.calls = []
        def execute(self, module, action, arguments):
            self.calls.append((module, action, arguments))
            return web(arguments['query'], arguments['filename'], arguments['limit'])

    def test_research_fetches_real_pages_before_synthesis_and_records_sources(self):
        manager = self.Manager()
        receipts = []
        messages = research_messages(manager, [{'role':'system','content':'Apollo'}], 'Retrieval research',
                                     used=lambda n,p: receipts.append(json.loads(p)))
        self.assertEqual(len(manager.calls), 1)
        self.assertEqual(manager.calls[0][1], 'explore_web_and_save')
        self.assertIn(QUOTE, messages[1]['content'])
        self.assertEqual(receipts[0]['sources'][0]['url'], URL)
        self.assertTrue(receipts[0]['sources'][0]['fetched'])
        self.assertEqual(messages[-1]['content'], 'Retrieval research')

    def test_deep_research_bounded_to_three_passes_and_source_dedup(self):
        manager = self.Manager()
        messages = research_messages(manager, [{'role':'system','content':'Apollo'}], 'Retrieval research', deep=True)
        self.assertEqual(len(manager.calls), 3)
        self.assertEqual(messages[1]['content'].count(URL), 1)
        self.assertTrue(all(c[2]['limit'] == 2 for c in manager.calls))

    def test_permission_failure_is_visible_not_model_only_success(self):
        manager = self.Manager()
        manager.execute = lambda *args: (_ for _ in ()).throw(PermissionError('web denied'))
        with self.assertRaisesRegex(RuntimeError, 'web denied'):
            research_messages(manager, [{'role':'system','content':'Apollo'}], 'Retrieval research')

    def test_cancel_between_passes_prevents_new_fetch_and_answer(self):
        manager = self.Manager()
        result = research_messages(manager, [{'role':'system','content':'Apollo'}], 'Retrieval research', deep=True,
                                   cancelled=lambda: bool(manager.calls))
        self.assertIsNone(result)
        self.assertEqual(len(manager.calls), 1)

    def test_no_tools_no_network_and_bounded_prompt(self):
        with self.assertRaises(PermissionError):
            research_messages(None, [], 'Topic')
        messages = research_messages(self.Manager(), [{'role':'system','content':'x'*15000}], 'q'*15000, max_chars=6000)
        self.assertLessEqual(sum(len(m['content']) for m in messages), 6000)


class MemoryRoutingTests(unittest.TestCase):
    def test_real_memory_bank_sink_routes_to_selected_or_auto_node_idempotently(self):
        from modules.memory_bank.module import Module as Bank
        from modules.learning_missions.module import Module as Learning
        with tempfile.TemporaryDirectory() as root:
            bank = Bank({'base_dir': root, 'validation': True})
            self.addCleanup(bank.close)
            class Manager:
                def execute(self, module, action, args):
                    self.assert_module = module
                    return bank.run(action, args)
            class Runtime: _manager = Manager()
            learning = Learning({'base_dir': root, 'runtime': Runtime(), 'validation': True})
            self.addCleanup(learning.close)
            mission = {'id': 5, 'title': 'Retrieval study', 'goal': 'Retrieval study', 'target_node_id': None}
            lesson = practitioner(mission['goal'], web('', '', 3))
            first = learning._save_lesson(mission, 1, lesson)
            retry = learning._save_lesson(mission, 1, lesson)
            self.assertEqual(first['id'], retry['id'])
            nodes = bank.memory_nodes(first['id'])
            self.assertIn('Research', [n['title'] for n in nodes])
            self.assertIn('Retrieval study', [n['title'] for n in nodes])
            self.assertEqual(bank.stats()['total_memories'], 1)
            target = bank.create_knowledge_node('My lab research', kind='project')
            mission['target_node_id'] = target['id']
            second = learning._save_lesson(mission, 2, lesson)
            self.assertIn(target['id'], [n['id'] for n in bank.memory_nodes(second['id'])])
            self.assertIn('Unverified', bank.knowledge_context('Retrieval study')['text'])

    def test_practice_rejects_cloud_endpoint_before_model_call(self):
        from modules.learning_missions.module import Module as Learning
        with tempfile.TemporaryDirectory() as root:
            (Path(root)/'config.json').write_text(json.dumps({'ollama_url':'https://cloud.example.org', 'model':'test'}))
            learning = Learning({'base_dir':root, 'validation':True})
            self.addCleanup(learning.close)
            with self.assertRaises(PermissionError):
                learning._practice('Retrieval study', web('', '', 3))


@unittest.skipIf(importlib.util.find_spec('PySide6') is None, 'Qt integration runs on Windows')
class WorkerRoutingTests(unittest.TestCase):
    def test_owner_command_not_decorated_by_research_mode_or_attachments(self):
        from workers import ChatTask
        from modules.learning_missions.module import Module as Learning
        with tempfile.TemporaryDirectory() as root:
            learning = Learning({'base_dir': root, 'validation': True})
            self.addCleanup(learning.close)
            class Manager:
                def get_module(self, name):
                    return {'enabled': True, 'instance': learning} if name == 'learning_missions' else None
            task = ChatTask(object(), [{'role':'user','content':'Search and cite: decorated request'}], Manager(),
                owner_text='start public practice on retrieval methods until I say stop', work_mode='Web research')
            text = task._run_with_modules()
            self.assertIn('Practice mission', text)
            self.assertEqual(learning.service.store.list()[0]['practice'], 1)

    def test_deep_mode_uses_research_pipeline_not_model_tool_guess(self):
        from workers import ChatTask
        manager = ResearchPipelineTests.Manager()
        class Client:
            num_ctx = 8192
            def stream_chat(self, messages):
                self.messages = messages
                yield 'An evidence-backed answer.'
        client = Client()
        task = ChatTask(client, [{'role':'system','content':'Apollo'}, {'role':'user','content':'Retrieval research'}],
                        manager, owner_text='Retrieval research', work_mode='Deep research')
        self.assertEqual(task._run_with_modules(), 'An evidence-backed answer.')
        self.assertEqual(len(manager.calls), 3)
        self.assertIn(URL, json.dumps(client.messages))


if __name__ == '__main__': unittest.main()
