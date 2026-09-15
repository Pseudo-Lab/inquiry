import re
import unittest

import branch_scenarios as scenarios
from presentation import cells


class ScenarioTests(unittest.TestCase):
    def test_headers_and_node_columns_align(self):
        for name in scenarios.SCENARIOS:
            for width in (80, 100, 120):
                text = scenarios.render(name, width)
                header = next(line for line in text.splitlines() if 'HYPOTHESIS' in line)
                self.assertIn('GRAPH', header)
                # Column separators should align in terminal cells, including Korean titles.
                def boundaries(line):
                    return [cells(line[:i]) for i, c in enumerate(line) if c == '│']
                expected = boundaries(header)
                for node in scenarios.SCENARIOS[name]['nodes']:
                    line = next(line for line in text.splitlines() if node.title in line)
                    self.assertEqual(boundaries(line)[-4:], expected[-4:])

    def test_dimensions_and_color(self):
        for name in scenarios.SCENARIOS:
            for width in (80, 100, 120):
                with self.subTest(name=name, width=width):
                    plain = scenarios.render(name, width)
                    colored = scenarios.render(name, width, color=True)
                    self.assertEqual(re.sub(r'\x1b\[[0-9;]*m', '', colored), plain)
                    self.assertTrue(all(cells(row) == width for row in plain.splitlines()))
                    self.assertNotIn('…', plain)

    def test_parent_order_is_acyclic(self):
        for name, scenario in scenarios.SCENARIOS.items():
            seen = set()
            for node in scenario['nodes']:
                self.assertNotIn(node.id, seen)
                self.assertTrue(set(node.parents) <= seen)
                seen.add(node.id)

    def test_merge_retains_both_inputs_and_continues(self):
        nodes = {n.id: n for n in scenarios.SCENARIOS['merge']['nodes']}
        self.assertEqual(set(nodes['SYN-01'].parents), {'H-002', 'H-007'})
        self.assertEqual(nodes['SYN-01'].state, 'exploring')
        for parent in nodes['SYN-01'].parents:
            self.assertEqual(nodes[parent].state, 'synthesized')
        self.assertEqual(nodes['H-008'].parents, ('SYN-01',))

    def test_ended_branches_are_not_silently_continued(self):
        nodes = scenarios.SCENARIOS['endings']['nodes']
        ended = {n.id for n in nodes if n.state in ('refuted', 'human-closed')}
        self.assertEqual(ended, {'H-007', 'H-005'})
        self.assertFalse(any(set(n.parents) & ended for n in nodes))
        text = scenarios.render('endings')
        self.assertIn('Refuted', text)
        self.assertIn('Closed by user', text)
        self.assertEqual(text.count('Reason:'), 2)
        self.assertEqual(text.count('Evidence:'), 2)
        self.assertEqual(text.count('Reopen:'), 2)


if __name__ == '__main__':
    unittest.main()
