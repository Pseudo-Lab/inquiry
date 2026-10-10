import copy
import unittest

from inquiry.graph import GraphError, validate_graph


class GraphTests(unittest.TestCase):
    def test_accepts_empty_disconnected_and_merged_dags_without_mutation(self):
        for graph in ({}, {'a': [], 'b': []},
                      {'a': [], 'b': ['a'], 'c': ['a'], 'd': ['b', 'c']},
                      {'a': (), 'b': ('a',)}):
            before = copy.deepcopy(graph)
            self.assertIsNone(validate_graph(graph))
            self.assertEqual(graph, before)

    def test_rejects_invalid_edges_and_cycles(self):
        for graph in ({'a': ['a']}, {'a': ['missing']},
                      {'a': [], 'b': ['a', 'a']},
                      {'a': ['c'], 'b': ['a'], 'c': ['b']}):
            with self.subTest(graph=graph), self.assertRaises(GraphError):
                validate_graph(graph)

    def test_rejects_invalid_identifiers_and_collections(self):
        for graph in ([], None, {1: []}, {'': []}, {' ': []},
                      {'a': [1]}, {'a': [None]}, {'a': [[]]},
                      {'a': 'a'}, {'a': None}, {'a': set()}):
            with self.subTest(graph=graph), self.assertRaises(GraphError):
                validate_graph(graph)

    def test_accepts_deep_dag_without_recursion_limit(self):
        graph = {str(i): [str(i - 1)] if i else [] for i in range(2000)}
        validate_graph(graph)
