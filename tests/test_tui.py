"""Headless tests for the M2-6 Textual TUI (map + arrow-key Details)."""
import tempfile
import unittest

from textual.widgets import DataTable, Static

from inquiry.commands import Commands
from inquiry.tui import InquiryTUI


class TUITests(unittest.IsolatedAsyncioTestCase):
    def _make(self, with_nodes=True):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        c = Commands(tmp.name)
        c.initialize('재택 생산성', {'central_question': '어떤 근무가 생산적인가?'})
        if with_nodes:
            a = c.add_hypothesis('전면 재택', '전면 재택은 비동기 흐름을 강화한다')
            c.decide(a, 'start')
            ev = c.add_evidence(a, 'supports', 'measured-result',
                                '리뷰 응답 12% 단축', '2026-10-07T00:00:00Z')
            c.decide(a, 'support', reason='측정 결과가 뒷받침', evidence_id=ev)
            c.add_hypothesis('하이브리드', '하이브리드가 균형을 제공한다')
        return tmp.name

    async def test_map_lists_hypotheses_and_arrow_updates_details(self):
        app = InquiryTUI(self._make())
        async with app.run_test(size=(120, 30)) as pilot:
            table = app.query_one('#map', DataTable)
            self.assertEqual(table.row_count, 2)
            d0 = str(app.query_one('#details', Static).render())
            self.assertIn('전면 재택', d0)
            await pilot.press('down')
            await pilot.pause()
            d1 = str(app.query_one('#details', Static).render())
            self.assertNotEqual(d0, d1)
            self.assertIn('하이브리드', d1)

    async def test_supported_node_details_show_status_and_evidence(self):
        app = InquiryTUI(self._make())
        async with app.run_test(size=(120, 30)) as pilot:
            d = str(app.query_one('#details', Static).render())
            self.assertIn('Supported', d)
            self.assertIn('measured-result', d)

    async def test_empty_inquiry_shows_placeholder(self):
        app = InquiryTUI(self._make(with_nodes=False))
        async with app.run_test(size=(80, 24)) as pilot:
            self.assertEqual(app.query_one('#map', DataTable).row_count, 0)
            self.assertIn('가설이 없', str(app.query_one('#details', Static).render()))


if __name__ == '__main__':
    unittest.main()
