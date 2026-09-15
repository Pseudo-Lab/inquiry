import re
import unittest

import scale
from presentation import cells


class ScaleTests(unittest.TestCase):
    def test_exact_sizes_and_valid_ancestry(self):
        for count in (10, 30, 100):
            dataset = scale.make_dataset(count)
            self.assertEqual(len(dataset.nodes), count)
            seen = {}
            for node in dataset.nodes:
                self.assertNotIn(node.id, seen)
                for parent in node.parents:
                    self.assertIn(parent, seen)
                    self.assertNotIn(seen[parent].state, ('refuted', 'human-closed'))
                    if seen[parent].state == 'synthesized':
                        self.assertEqual(len(node.parents), 2)
                seen[node.id] = node
            self.assertTrue(any(len(n.parents) == 2 for n in dataset.nodes))
            if count >= 30:
                self.assertTrue(any(n.state == 'refuted' for n in dataset.nodes))
                self.assertTrue(any(n.state == 'human-closed' for n in dataset.nodes))

    def test_all_matrix_pages_fit_and_recover_every_node(self):
        for width in (80, 120, 160):
            for count in (10, 30, 100):
                dataset = scale.make_dataset(count)
                recovered = set()
                for page in range(1, len(dataset.groups) + 1):
                    view = scale.render(width, count, page)
                    colored = scale.render(width, count, page, color=True)
                    self.assertEqual(re.sub(r'\x1b\[[0-9;]*m', '', colored.text), view.text)
                    self.assertEqual(len(view.text.splitlines()), 40)
                    self.assertTrue(all(cells(line) == width for line in view.text.splitlines()))
                    self.assertNotIn('…', view.text)
                    self.assertEqual(len(view.visible) + view.hidden, count)
                    self.assertIn(view.context, view.visible)
                    for node in dataset.groups[page - 1]['nodes'][1:]:
                        self.assertTrue(set(node.parents) <= set(view.visible))
                    recovered.update(view.visible)
                self.assertEqual(recovered, {n.id for n in dataset.nodes})

    def test_context_is_previous_groups_live_endpoint(self):
        dataset = scale.make_dataset(100)
        for before, after in zip(dataset.groups, dataset.groups[1:]):
            self.assertEqual(after['nodes'][0], before['nodes'][-1])

    def test_invalid_cli_inputs(self):
        for args in ({'width': 79}, {'count': 11}, {'page': 0}, {'page': 1000}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                scale.render(**args)


if __name__ == '__main__':
    unittest.main()
