"""Initiative Director regression tests. No network, Ollama or UI required."""
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from apollo_initiative import InitiativeDirector


class RuntimeStub:
    def __init__(self, file):
        self.conn = sqlite3.connect(file, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self.conn.execute("""CREATE TABLE IF NOT EXISTS goals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,
            status TEXT NOT NULL,priority INTEGER NOT NULL,notes TEXT NOT NULL,
            created_at TEXT NOT NULL,updated_at TEXT NOT NULL)""")
        self.conn.commit()


class SuggestionsStub:
    def __init__(self):
        self.items = []
        self.calls = 0

    def add(self, kind, title, prompt, reason, evidence=()):
        self.calls += 1
        for entry in self.items:
            if entry['kind'] == kind and entry['title'].casefold() == title.casefold():
                return entry
        item = dict(id=len(self.items)+1, kind=kind, title=title,
                    prompt=prompt, reason=reason, evidence=list(evidence),
                    status='open')
        self.items.append(item)
        return item

    def list(self):
        return list(self.items)


class InitiativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / 'runtime.db')
        self.runtime = RuntimeStub(self.path)
        self.addCleanup(self.runtime.conn.close)
        self.suggestions = SuggestionsStub()
        self.director = InitiativeDirector(self.runtime, self.suggestions)

    def goal(self, title='Improve Apollo latency', priority=75, **kw):
        return self.director.create_goal(title, 'Reduce local model response latency',
                                         priority=priority, owner_confirmed=True, **kw)

    def test_owner_only_and_input_validation(self):
        with self.assertRaises(PermissionError):
            self.director.create_goal('My goal', 'A measurable improvement')
        with self.assertRaises(ValueError):
            self.goal(priority=101)
        with self.assertRaises(ValueError):
            self.goal(title='bad')
        self.assertEqual(self.director.goals(), [])

    def test_creates_goal_in_shared_runtime_database(self):
        g = self.goal()
        row = self.runtime.conn.execute('SELECT * FROM goals WHERE id=?', (g['id'],)).fetchone()
        self.assertEqual(row['title'], 'Improve Apollo latency')
        self.assertEqual(self.director.goal(g['id'])['desired_outcome'], 'Reduce local model response latency')
        with self.assertRaises(ValueError):
            self.goal()

    def test_goal_hierarchy_and_parent_validation(self):
        parent = self.goal()
        child = self.goal('Improve model load times', parent_goal_id=parent['id'])
        self.assertEqual(child['parent_goal_id'], parent['id'])
        with self.assertRaises(ValueError):
            self.goal('My next child', parent_goal_id=99)
        self.director.set_goal_status(parent['id'], 'paused', owner_confirmed=True)
        with self.assertRaises(ValueError):
            self.goal('A third objective', parent_goal_id=parent['id'])

    def test_goal_status_requires_owner_and_blocks_step(self):
        g = self.goal()
        with self.assertRaises(PermissionError):
            self.director.set_goal_status(g['id'], 'stopped')
        self.director.set_goal_status(g['id'], 'stopped', owner_confirmed=True)
        with self.assertRaises(ValueError):
            self.director.propose_step(g['id'], owner_confirmed=True)

    def test_manual_self_prompt_never_executes_and_deduplicates(self):
        g = self.goal()
        with self.assertRaises(PermissionError):
            self.director.propose_step(g['id'])
        self.assertEqual(self.suggestions.calls, 0)
        item = self.director.propose_step(g['id'], owner_confirmed=True)
        again = self.director.propose_step(g['id'], owner_confirmed=True)
        self.assertEqual(item['id'], again['id'])
        self.assertEqual(len(self.suggestions.items), 1)
        self.assertIn('do not run tools', item['prompt'])
        self.assertIn('Owner', item['reason'])
        count = self.runtime.conn.execute('SELECT count(*) FROM initiative_step_links').fetchone()
        self.assertEqual(count[0], 1)

    def test_rank_is_deterministic_and_skips_dismissed(self):
        g = self.goal(priority=95)
        matched = self.director.propose_step(g['id'], owner_confirmed=True)
        other = self.suggestions.add('proposal', 'Explore unrelated art',
                                     'Look for visual styles', 'Just a suggestion')
        self.suggestions.add('question', 'Ask a question', 'What matters?', 'Guidance needed')
        ranks = self.director.ranked_proposals()
        self.assertEqual(ranks[0]['suggestion_id'], matched['id'])
        self.assertEqual(len(ranks), 2)
        self.assertEqual(ranks[0]['goal_id'], g['id'])
        self.assertEqual(ranks, self.director.ranked_proposals())
        other['status'] = 'dismissed'
        self.assertEqual(len(self.director.ranked_proposals()), 1)

    def test_restart_preserves_meta_and_links(self):
        g = self.goal()
        self.director.propose_step(g['id'], owner_confirmed=True)
        self.runtime.conn.close()
        runtime = RuntimeStub(self.path)
        try:
            restored = InitiativeDirector(runtime, self.suggestions)
            self.assertEqual(restored.goal(g['id'])['title'], g['title'])
            self.assertEqual(restored.ranked_proposals()[0]['goal_id'], g['id'])
        finally:
            runtime.conn.close()

    def test_bounded_active_goals(self):
        for i in range(40):
            self.goal(f'Goal number {i} benchmark')
        with self.assertRaises(ValueError):
            self.goal('Another major benchmark goal')
        self.assertEqual(len(self.director.goals(limit=50)), 40)


if __name__ == '__main__':
    unittest.main()
