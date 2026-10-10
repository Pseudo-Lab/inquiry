import json
import copy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from inquiry.commands import Commands
from inquiry.replay import replay, ReplayError
from inquiry.store import Store


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.commands = Commands(self.root)
        self.commands.initialize('seed', {'question': 'question'})

    def add(self, parents=()):
        return self.commands.add_hypothesis('title', 'claim', parents)

    def evidence(self, target, relation='supports'):
        return self.commands.add_evidence(target, relation, 'human-judgment',
            '직접 확인한 판단', '2026-09-19T00:00:00Z')

    def test_human_journey_to_two_parent_synthesis_and_restart(self):
        left, right = self.add(), self.add()
        self.commands.decide(left, 'start')
        self.commands.decide(right, 'start')
        evidence = self.evidence(left)
        self.commands.link_evidence(evidence, right, 'challenges')
        self.commands.decide(left, 'support', reason='observed', evidence_id=evidence)
        self.commands.decide(right, 'contest', reason='counterexample', evidence_id=evidence)
        merged = self.commands.synthesize([left, right], 'combined', 'combined claim', 'human decision')
        state = replay(Store(self.root).read_all())
        self.assertEqual(state.hypotheses[merged].parent_ids, (left, right))
        self.assertEqual(state.hypotheses[merged].status, 'suggested')
        self.assertEqual(state.hypotheses[left].status, 'synthesized')
        self.assertEqual(state.hypotheses[right].synthesis_target, merged)
        self.assertEqual(len(state.evidence_links), 2)
        child = self.add()
        self.assertNotIn(child, (left, right, merged))

    def test_refuted_and_closed_keep_snapshots_and_need_human_reopen(self):
        target = self.add()
        self.commands.decide(target, 'start')
        evidence = self.evidence(target, 'challenges')
        self.commands.decide(target, 'refute', reason='counterexample', evidence_id=evidence,
                             reopen_if='new conditions')
        state = self.commands.state()
        self.assertEqual(state.hypotheses[target].evidence_snapshot['items'][0]['content'], '직접 확인한 판단')
        self.commands.decide(target, 'reopen', reason='conditions changed', evidence_id=evidence)
        self.assertEqual(self.commands.state().hypotheses[target].status, 'exploring')
        rejected = self.add()
        self.commands.decide(rejected, 'close', reason='out of scope', reopen_if='scope changes')
        node = self.commands.state().hypotheses[rejected]
        self.assertEqual(node.status, 'human-closed')
        self.assertEqual(node.evidence_snapshot['items'], [])
        self.assertTrue(node.evidence_snapshot['note'])

    def test_invalid_decision_has_no_partial_writes(self):
        target, other = self.add(), self.add()
        self.commands.decide(target, 'start')
        unrelated = self.evidence(other)
        before = Store(self.root).path.read_bytes()
        for action in [lambda: self.commands.decide(target, 'close', reason='no', reopen_if='later'),
                       lambda: self.commands.decide(target, 'support', reason='no', evidence_id=unrelated),
                       lambda: self.commands.synthesize([target, other], 't', 'c', 'reason'),
                       lambda: self.commands.add_hypothesis('t', 'c', ['missing'])]:
            with self.assertRaises(ValueError):
                action()
            self.assertEqual(Store(self.root).path.read_bytes(), before)

    def test_evidence_type_relation_and_duplicate_link(self):
        target = self.add()
        before = Store(self.root).path.read_bytes()
        for kind, uri in [('llm-opinion', None), ('external-article', None), ('dataset', '')]:
            with self.assertRaises(ValueError):
                self.commands.add_evidence(target, 'supports', kind, 'content', '2026-09-19T00:00:00Z', uri)
            self.assertEqual(Store(self.root).path.read_bytes(), before)
        evidence = self.evidence(target)
        before = Store(self.root).path.read_bytes()
        with self.assertRaises(ValueError):
            self.commands.link_evidence(evidence, target, 'supports')
        self.assertEqual(Store(self.root).path.read_bytes(), before)

    def test_cli_journey_and_snapshot_of_file(self):
        def cli(*args, ok=True):
            result = subprocess.run([sys.executable, '-m', 'inquiry', '--dir', str(self.root), *args],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode == 0, ok, result.stderr)
            return json.loads(result.stdout) if ok else result
        left = cli('hypothesis', 'add', '--title', 'left', '--claim', 'left claim')['id']
        right = cli('hypothesis', 'add', '--title', 'right', '--claim', 'right claim')['id']
        path = self.root / 'evidence.md'
        path.write_text('original observation', encoding='utf-8')
        for target in (left, right):
            cli('start', target)
            record = cli('evidence', 'add', target, '--supports', '--file', str(path),
                         '--type', 'human-judgment', '--retrieved-at', '2026-09-19T00:00:00Z')
            cli('support', target, '--evidence', record['id'], '--reason', 'confirmed')
        path.write_text('changed later', encoding='utf-8')
        merged = cli('synthesize', left, right, '--title', 'merge', '--claim', 'both', '--reason', 'combine')['id']
        self.assertEqual(cli('show', merged)['parent_ids'], [left, right])
        self.assertEqual(self.commands.state().evidence['E-001'].content, 'original observation')
        cli('start', merged, '--by', 'agent', ok=False)

    def test_forged_transition_actor_and_snapshot_are_rejected(self):
        target = self.add()
        self.commands.decide(target, 'start')
        evidence = self.evidence(target, 'challenges')
        self.commands.decide(target, 'refute', reason='observed', evidence_id=evidence, reopen_if='new context')
        history = Store(self.root).read_all()
        for mutation in ('actor', 'snapshot', 'from'):
            corrupted = copy.deepcopy(history)
            change = corrupted[-1]['changes'][0]
            if mutation == 'actor':
                change['actor'] = 'agent:fake'
            elif mutation == 'snapshot':
                change['evidence_snapshot']['items'][0]['content'] = 'invented'
            else:
                change['from'] = 'suggested'
            with self.subTest(mutation=mutation), self.assertRaises(ReplayError):
                replay(corrupted)

    def test_partial_synthesis_cannot_commit(self):
        left, right = self.add(), self.add()
        for target in (left, right):
            self.commands.decide(target, 'start')
            evidence = self.evidence(target)
            self.commands.decide(target, 'support', reason='confirmed', evidence_id=evidence)
        before_events = Store(self.root).read_all()
        self.commands.synthesize([left, right], 'both', 'claim', 'merge')
        proposal = Store(self.root).read_all()[-1]
        proposal['changes'].pop()
        other = self.root / 'other'
        with Store(other) as store:
            for prior in before_events:
                store.append(prior, expected_seq=prior['seq'] - 1)
            before = store.path.read_bytes()
            with self.assertRaises(ReplayError):
                store.append(proposal, expected_seq=len(before_events))
            self.assertEqual(store.path.read_bytes(), before)

    def test_relative_command_root_is_stable(self):
        previous = Path.cwd()
        try:
            os.chdir(self.root.parent)
            commands = Commands(self.root.name)
            os.chdir(previous)
            self.assertEqual(commands.state().inquiry_id, self.commands.state().inquiry_id)
        finally:
            os.chdir(previous)


if __name__ == '__main__':
    unittest.main()
