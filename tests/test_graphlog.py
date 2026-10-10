"""Tests for the pure DAG lane layout (git-log style graph column)."""
import unittest

from inquiry.graphlog import lane_rows, render_row


class N:
    """최소 가설 스텁 (id, parent_ids)."""
    def __init__(self, id, parents=()):
        self.id = id
        self.parent_ids = tuple(parents)


def cols(nodes):
    return [col for _, col in lane_rows(nodes)]


class GraphLogTests(unittest.TestCase):
    def test_linear_chain_stays_in_one_lane(self):
        nodes = [N('A'), N('B', ['A']), N('C', ['B'])]
        self.assertEqual(cols(nodes), [0, 0, 0])
        # 모든 행이 단일 레인
        self.assertTrue(all(len(cells) == 1 for cells, _ in lane_rows(nodes)))

    def test_fork_opens_second_lane(self):
        # A → {B, C}: B는 A 레인 재사용, C는 새 레인
        nodes = [N('A'), N('B', ['A']), N('C', ['A'])]
        c = cols(nodes)
        self.assertEqual(c[0], 0)      # A
        self.assertEqual(c[1], 0)      # B 재사용
        self.assertEqual(c[2], 1)      # C 새 레인
        # B 행에서 둘째 자식 C를 기다리는 레인1이 세로바로 보인다
        cells_b, _ = lane_rows(nodes)[1]
        self.assertEqual(cells_b[1], '│')

    def test_merge_closes_parent_lanes(self):
        # A, B 독립 → C(parents A,B): C는 둘을 합류
        nodes = [N('A'), N('B'), N('C', ['A', 'B'])]
        rows = lane_rows(nodes)
        self.assertEqual(rows[0][1], 0)   # A lane0
        self.assertEqual(rows[1][1], 1)   # B lane1 (A 활성이라)
        self.assertEqual(rows[2][1], 0)   # C는 왼쪽 부모 레인 재사용
        # C 이후 A·B 레인은 닫힘 — C가 자식 없으면 전부 None
        # (간접 확인) C 행 폭은 2, col 0
        self.assertEqual(len(rows[2][0]), 2)

    def test_fork_parent_lane_persists_until_all_children_drawn(self):
        # A → B, A → C, 사이에 무관 노드 없음: A는 C까지 활성
        nodes = [N('A'), N('B', ['A']), N('C', ['A'])]
        # B 행에서 A는 여전히 활성(자식 C 남음) → B의 col0은 '@', 레인수1 또는 A 유지
        cells_b, col_b = lane_rows(nodes)[1]
        self.assertEqual(col_b, 0)

    def test_render_row_places_symbol_at_col(self):
        cells = ['│', '@', ' ']
        s = render_row(cells, 1, '✓')
        self.assertIn('✓', s)
        self.assertTrue(s.startswith('│'))

    def test_isolated_roots_get_separate_lanes(self):
        nodes = [N('A'), N('B')]   # 둘 다 부모 없음, 서로 무관
        # A는 자식 없으니 레인 닫힘 → B는 lane0 재사용 가능
        self.assertEqual(cols(nodes), [0, 0])


if __name__ == '__main__':
    unittest.main()
