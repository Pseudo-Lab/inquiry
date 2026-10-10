"""Headless tests for the M2-6 Textual TUI (map + arrow-key Details + ops)."""
import asyncio
import tempfile
import threading
import unittest

from textual.widgets import DataTable, Static

from inquiry.adapter import RunSignal
from inquiry.commands import Commands
from inquiry.tui import InquiryTUI
from tests.fakes import FakeAdapter
from tests.operation_fixtures import challenge_output


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


class TUIOperationTests(unittest.IsolatedAsyncioTestCase):
    def _make(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        c = Commands(tmp.name)
        c.initialize('seed', {'central_question': 'q'})
        self.hid = c.add_hypothesis('가설1', '가설1은 성립할 수 있다')  # suggested → op 적격
        return tmp.name

    async def test_start_command_transitions_highlighted_node(self):
        root = self._make()
        app = InquiryTUI(root)
        async with app.run_test(size=(100, 24)) as pilot:
            app._dispatch('start')
            await pilot.pause()
        self.assertEqual(Commands(root).state().hypotheses[self.hid].status, 'exploring')

    async def test_challenge_proposes_then_accept_persists_note(self):
        root = self._make()
        factory = lambda: (FakeAdapter([RunSignal('succeeded', proposal=challenge_output())]), 'fake')
        app = InquiryTUI(root, op_factories={'challenge': factory})
        async with app.run_test(size=(100, 24)) as pilot:
            app._start_op('challenge')
            await app._op_worker.wait()
            await pilot.pause()
            self.assertIsNotNone(app.pending)
            self.assertIn('제안 생성', str(app.query_one('#status', Static).render()))
            app._accept()
            await pilot.pause()
        self.assertIsNone(app.pending)
        self.assertEqual(len(Commands(root).state().review_notes), 1)

    async def test_read_only_without_adapter_reports_and_no_change(self):
        root = self._make()
        app = InquiryTUI(root)  # op_factories 없음
        async with app.run_test(size=(100, 24)) as pilot:
            app._start_op('challenge')
            await pilot.pause()
            self.assertIsNone(app.pending)
            self.assertIn('어댑터가 설정되지 않', str(app.query_one('#status', Static).render()))

    async def test_fork_proposes_candidates_then_accept_creates_children(self):
        from tests.branch_fixtures import branch_output
        root = self._make()
        factory = lambda: (FakeAdapter([RunSignal('succeeded', proposal=branch_output())]), 'fake')
        app = InquiryTUI(root, op_factories={'fork': factory})
        async with app.run_test(size=(100, 24)) as pilot:
            app._start_fork()
            await app._op_worker.wait()
            await pilot.pause()
            self.assertEqual(app.pending_kind, 'branch')
            self.assertIn('fork 제안', str(app.query_one('#status', Static).render()))
            app._accept('1 2')   # 후보 2개만 선택 승인
            await pilot.pause()
        self.assertIsNone(app.pending)
        self.assertEqual(len(Commands(root).state().hypotheses), 3)  # 부모 1 + 자식 2

    async def test_synthesize_marks_two_parents_then_accept_creates_node(self):
        from tests.operation_fixtures import supported_pair, synthesis_output
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p1, p2 = supported_pair(tmp.name)   # 두 supported 부모
        factory = lambda: (FakeAdapter([RunSignal('succeeded', proposal=synthesis_output())]), 'fake')
        app = InquiryTUI(tmp.name, op_factories={'synthesize': factory})
        async with app.run_test(size=(100, 24)) as pilot:
            app._dispatch('synthesize')   # 아직 mark 없음 → 거부
            await pilot.pause()
            self.assertIn('2개 이상', str(app.query_one('#status', Static).render()))
            app._find(p1); app._toggle_mark()
            app._find(p2); app._toggle_mark()
            self.assertEqual(len(app.marked), 2)
            app._start_synth()
            await app._op_worker.wait()
            await pilot.pause()
            self.assertEqual(app.pending_kind, 'op')
            before = len(Commands(tmp.name).state().hypotheses)
            app._accept()
            await pilot.pause()
            self.assertEqual(len(app.marked), 0)   # 승인 후 표시 해제
        state = Commands(tmp.name).state()
        self.assertEqual(len(state.hypotheses), before + 1)   # 통합 가설 1개 생성
        self.assertTrue(any(h.status == 'synthesized' for h in state.hypotheses.values()))

    async def test_find_jumps_cursor_to_node_id(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        c = Commands(tmp.name)
        c.initialize('seed', {'central_question': 'q'})
        ids = [c.add_hypothesis(f'가설{i}', f'가설{i} 성립') for i in range(5)]
        app = InquiryTUI(tmp.name)
        async with app.run_test(size=(100, 24)) as pilot:
            app._dispatch(f'find {ids[3]}')
            await pilot.pause()
            self.assertEqual(app.query_one('#map', DataTable).cursor_row, 3)
            self.assertIn(ids[3], str(app.query_one('#status', Static).render()))
            app._dispatch('find H-999')
            await pilot.pause()
            self.assertIn('찾을 수 없', str(app.query_one('#status', Static).render()))

    async def test_status_symbols_are_distinct_shapes(self):
        from inquiry.tui import STATUS
        symbols = [sym for sym, _ in STATUS.values()]
        self.assertEqual(len(symbols), len(set(symbols)))  # 전부 고유
        # 원 계열 중복 제거 확인: 지지/탐색/제안이 서로 다른 글리프
        self.assertNotEqual(STATUS['supported'][0], STATUS['exploring'][0])
        self.assertNotEqual(STATUS['exploring'][0], STATUS['suggested'][0])

    async def test_running_op_can_be_cancelled(self):
        root = self._make()
        started, release = threading.Event(), threading.Event()

        class BlockingAdapter:
            def run(self, request):
                yield RunSignal('progress', text='w1')
                started.set()
                release.wait(3)
                yield RunSignal('progress', text='w2')  # cancel seen between signals
                yield RunSignal('succeeded', proposal=challenge_output())

        factory = lambda: (BlockingAdapter(), 'fake')
        app = InquiryTUI(root, op_factories={'challenge': factory})
        async with app.run_test(size=(100, 24)) as pilot:
            app._start_op('challenge')
            for _ in range(150):
                if started.is_set():
                    break
                await asyncio.sleep(0.02)
            self.assertTrue(started.is_set(), '워커가 시작되지 않음')
            app.action_cancel_op()   # worker.cancel() → is_cancelled
            release.set()
            # 스레드가 협조적 취소로 끝나며 call_from_thread로 '취소됨'을 보고할 때까지 폴링
            status = ''
            for _ in range(150):
                status = str(app.query_one('#status', Static).render())
                if '취소됨' in status:
                    break
                await asyncio.sleep(0.02)
        self.assertIn('취소됨', status)
        self.assertIsNone(app.pending)
        self.assertEqual(len(Commands(root).state().review_notes), 0)


if __name__ == '__main__':
    unittest.main()
