"""Line-oriented Framing UI. No provider imports, direct writes, or TUI state."""
import importlib
import os
import re
import sys

from inquiry.features.framing.service import FramingService


class _Exit(Exception):
    pass


def _terminal_input(prompt):
    if sys.stdin.isatty() and sys.stdout.isatty():
        try:
            # Import installs Python's line editor; bare input can erase UTF-8 bytes.
            importlib.import_module('readline')
        except ImportError:
            raise ValueError('Terminal editing requires Python with readline support.') from None
    return input(prompt)


def _safe(value):
    """Render terminal control bytes visibly without changing stored text."""
    return ''.join(c if c in '\n\t' or (ord(c) >= 32 and not 127 <= ord(c) <= 159)
                   else f'\\x{ord(c):02x}' for c in str(value))


# 색·굵기(SGR)만 통과시키는 패턴 — 커서 이동·OSC 등 다른 제어열은 여전히 차단.
_SGR = re.compile(r'\x1b\[[0-9;]*m')


class _Console:
    def __init__(self, read, write):
        self.read = read or _terminal_input
        self.write = write or print
        # 스타일은 실제 터미널 출력일 때만 — 주입된 write(테스트·파이프)는 평문.
        self.styled = write is None and sys.stdout.isatty() and not os.environ.get('NO_COLOR')

    def _sgr(self, text, code):
        return f'\x1b[{code}m{text}\x1b[0m' if self.styled else text

    def bold(self, text):
        return self._sgr(text, '1')

    def accent(self, text):
        return self._sgr(text, '1;36')   # bold cyan — 제목·선택지 포인트

    def dim(self, text):
        return self._sgr(text, '2')

    def line(self, text=''):
        text = str(text)
        if self.styled and '\x1b[' in text:
            # 스타일 조각(SGR)은 보존하고 그 사이 내용만 소독한다.
            parts = _SGR.split(text)
            codes = _SGR.findall(text)
            text = _safe(parts[0]) + ''.join(code + _safe(part)
                                             for code, part in zip(codes, parts[1:]))
            self.write(text)
            return
        self.write(_safe(text))

    def head(self, title):
        """섹션 머리 — 긴 출력 사이 시각적 경계(가독성 피드백 2026-10-10)."""
        self.line()
        self.line(self.accent(f'── {title} ' + '─' * max(4, 56 - len(title) * 2)))

    def text(self, prompt):
        while True:
            value = self.read(prompt)
            if value.strip() == '/exit':
                raise _Exit()
            if value.strip():
                return value
            self.line('내용을 입력해 주세요. 모르면 "모르겠어요", 종료는 /exit입니다.')

    def choose(self, *labels):
        self.line()
        for index, label in enumerate(labels, 1):
            self.line(self.accent(f'{index}.') + f' {label}')
        choices = {str(index): index for index in range(1, len(labels) + 1)}
        while True:
            value = self.text('선택 > ').strip()
            if value in choices:
                return choices[value]
            self.line(f'1~{len(labels)} 중 번호를 입력해 주세요.')


def _candidates(console, candidates):
    """가설 후보 블록 — 번호·제목을 강조하고 후보 사이를 비워 덩어리로 구분."""
    for index, candidate in enumerate(candidates, 1):
        console.line(console.accent(f"  {index}. {candidate['title']}"))
        console.line(f"     주장      {candidate['claim']}")
        console.line('     ' + console.bold('다른 점   ') + candidate['difference'])
        console.line()


def _frame(console, frame):
    console.head('Frame proposal — 프레임 제안')
    console.line(console.bold('중심 질문  ') + frame['central_question'])
    for key, label in (('purpose', '목적      '), ('use_context', '사용 맥락 '),
                       ('current_belief', '현재 믿음 ')):
        console.line(console.bold(label) + frame[key])
    for label, items in (('판단 기준', frame['criteria']), ('범위 — 포함', frame['scope']['include']),
                         ('범위 — 제외', frame['scope']['exclude']),
                         ('열린 질문', frame['open_questions'])):
        console.line(console.bold(label + ':'))
        for item in items:
            console.line('  · ' + item)
        if not items:
            console.line(console.dim('  (없음)'))
    console.head('초기 가설 후보')
    console.line(console.dim('  수락(Accept)하면 아래 후보가 모두 생성됩니다. 일부만 원하면 거부 사유에 적어주세요.'))
    console.line()
    _candidates(console, frame['hypotheses'])


def _summary(console, state):
    console.head('저장된 탐구')
    console.line(console.bold('중심 질문  ') + str(state.inquiry.frame.get(
        'central_question', state.inquiry.frame.get('question', '미정'))))
    console.line(console.dim('Seed: ' + state.inquiry.seed))
    console.line()
    for identity in state.inquiry.hypothesis_ids:
        node = state.hypotheses[identity]
        parents = (' ← ' + ', '.join(node.parent_ids)) if node.parent_ids else ''
        console.line(console.accent(f'{node.id}') + f' [{node.status}] '
                     + console.bold(node.title) + console.dim(parents))
        console.line('    ' + node.claim)
    console.line()
    console.line(console.dim('그래프로 보려면: inquiry --dir <디렉토리> tui'))


def _run_status(console, run, *, recovered=False):
    label = 'Recovered run' if recovered else 'Run'
    suffix = f' / {run.reason}' if run.reason else ''
    console.line(f'{label}: {run.status}{suffix}')
    if run.status == 'cancelled' and run.reason == 'timeout':
        console.line(f'시간 초과 — 앱의 실행 제한 {run.timeout:g}초가 지났습니다. '
                     '제출한 답변은 저장되어 있으며 자동 재시도하지 않습니다.')
    console.line(f'Provider outcome: {run.provider_outcome}')
    if run.provider_outcome == 'unknown':
        console.line('공급자가 처리를 마쳤는지는 확인할 수 없습니다. 다시 생성하면 별도 요청이 됩니다.')
    if run.usage['status'] == 'unknown':
        console.line('Usage: unknown — 사용량 미확인 (0이 아닙니다).')
    else:
        console.line(f"Usage: input {run.usage['input_tokens']}, output {run.usage['output_tokens']}")


def _branch_selection(console, candidates):
    choices = {str(index): c['candidate_id'] for index, c in enumerate(candidates, 1)}
    while True:
        text = console.text('승인할 후보 번호 (예: 1,3 또는 all) > ').strip()
        if text.casefold() == 'all':
            return list(choices.values())
        numbers = text.replace(',', ' ').split()
        if numbers and len(set(numbers)) == len(numbers) and all(n in choices for n in numbers):
            return [choices[n] for n in numbers]
        console.line('표시된 후보 번호를 중복 없이 입력해 주세요.')


def _branch_once(console, root, factory, max_output_tokens, timeout):
    from inquiry.features.branch.service import BranchService
    from inquiry.features.branch.schema import BRANCH_PARENT_STATES
    service = BranchService(root)
    state = service.state()
    pending = {p['parent_id']: p for p in state.branch_proposals.values() if p['status'] == 'pending'}
    parents = [h for h in state.hypotheses.values()
               if h.status in BRANCH_PARENT_STATES or h.id in pending]
    if not parents:
        console.line('분기할 수 있는 가설이 없습니다. 허용 상태의 다른 가설을 선택해야 합니다.')
        return
    console.line('Parent — 이어서 탐구할 가설을 선택하세요.')
    labels = [f"{h.title} [{h.status}]" + (' / saved proposal' if h.id in pending else '') for h in parents]
    choice = console.choose(*labels, 'Back')
    if choice > len(parents):
        return
    parent = parents[choice - 1]
    if parent.id in pending:
        proposal = service.view(pending[parent.id]['id'])
    else:
        console.line('AI가 자식 가설 후보를 제안합니다. 승인 전에는 그래프를 바꾸지 않습니다.')
        if console.choose('Generate branches', 'Back') == 2:
            return
        before_runs = set(service.state().runs)
        try:
            proposal = service.propose(parent.id, adapter_factory=factory,
                                       max_output_tokens=max_output_tokens or 4000, timeout=timeout)
        except ValueError as error:
            console.line('Error: ' + str(error))
            for identity, run in service.state().runs.items():
                if identity not in before_runs:
                    _run_status(console, run)
            return
        _run_status(console, service.state().runs[proposal['run_id']])
    if proposal['status'] != 'pending':
        console.line('이 제안은 이미 처리됐습니다. 저장된 상태를 다시 표시합니다.')
        return
    console.head(f'Branch proposal — {parent.id} {parent.title} 아래 자식 후보')
    console.line(console.dim('  번호로 일부만 골라 수락할 수 있습니다 (Accept Selected → 예: 1,3 또는 all).'))
    console.line()
    _candidates(console, proposal['candidates'])
    try:
        if proposal['stale']:
            console.line('Stale — 부모가 바뀌어 승인할 수 없습니다. 거부 후 허용 부모에서 다시 생성하세요.')
            if console.choose('Reject', 'Save & Exit') == 2:
                raise _Exit()
            service.reject(proposal['id'], console.text('거부 이유 > '))
        else:
            choice = console.choose('Accept Selected', 'Reject', 'Save & Exit')
            if choice == 3:
                raise _Exit()
            if choice == 1:
                selected = _branch_selection(console, proposal['candidates'])
                mapping = service.accept(proposal['id'], selected)
                console.line('Branch saved: ' + ', '.join(mapping.values()))
            else:
                service.reject(proposal['id'], console.text('거부 이유 > '))
                console.line('Rejected — 새 후보는 다음 Branch/Generate 선택 때만 만듭니다.')
    except ValueError as error:
        console.line('Error: ' + str(error))


def _branch_workspace(console, root, factory, max_output_tokens, timeout,
                      operation_factories):
    from inquiry.features.branch.service import BranchService
    from inquiry.llm.runs import Runner
    service = BranchService(root)
    while True:
        state = service.state()
        if state.inquiry is None:
            raise ValueError('Inquiry no longer exists; reload the saved state.')
        _summary(console, state)
        totals = Runner(root).totals()
        console.line(f"Known tokens: input {totals['input_tokens']}, output {totals['output_tokens']}"
                     f" | Unknown runs: {totals['unknown_runs']}")
        interrupted = [r.id for r in state.runs.values() if r.status == 'started']
        if interrupted:
            console.line('Paused — 미종결 실행을 복구해야 새 실행을 시작할 수 있습니다.')
            if console.choose('Resume', 'Save & Exit') == 2:
                raise _Exit()
            Runner(root).recover()
            recovered = service.state()
            for identity in interrupted:
                _run_status(console, recovered.runs[identity], recovered=True)
            continue
        choice = console.choose('Branch', 'Save & Exit', 'Check')
        if choice == 2:
            raise _Exit()
        if choice == 1:
            _branch_once(console, root, factory, max_output_tokens, timeout)
        else:
            # Lazy import avoids interactive <-> operation_ui import cycles at load time.
            from inquiry.features.operation import ui as operation_ui
            operation_ui.run_check(console, root, operation_factories,
                                   max_output_tokens, timeout)


def run_conversation(root, *, adapter_factory, read=None, write=None,
                     max_output_tokens=None, timeout=60.0, branch_factory=None,
                     operation_factories=None):
    """Run a saved-state driven conversation, returning without automatic retry."""
    console = _Console(read, write)
    service = FramingService(root)
    console.line('Inquiry / Framing')
    console.line('한 줄씩 입력하고 Enter를 누르세요. /exit 또는 Ctrl-C로 종료할 수 있습니다.')
    console.line('제출한 답변은 즉시 저장됩니다. 새 질문·프레임 생성에는 API 사용료가 발생할 수 있습니다.')
    operation_factories = operation_factories or {
        kind: adapter_factory for kind in ('deepen', 'challenge', 'synthesize')}
    try:
        state = service.state()
        if state.inquiry is not None:
            _branch_workspace(console, root, branch_factory or adapter_factory, max_output_tokens,
                              timeout, operation_factories)
            return
        sessions = list(state.framing_sessions.values())
        if not sessions:
            sid = service.start(console.text('지금 탐구하고 싶은 생각을 적어주세요 > '))
        elif len(sessions) == 1:
            sid = sessions[0].id
        else:
            console.line('\nResume — 이어갈 초안을 선택하세요.')
            selected = console.choose(*[f'{s.seed} [{s.status}]' for s in sessions], 'Save & Exit')
            if selected > len(sessions):
                raise _Exit()
            sid = sessions[selected - 1].id
        console.line('Seed: ' + service.view(sid)['seed'])
        while True:
            state = service.state()
            if state.inquiry is not None:
                _branch_workspace(console, root, branch_factory or adapter_factory, max_output_tokens,
                                  timeout, operation_factories)
                return
            view = service.view(sid)
            if view['status'] == 'cancelled' or any(r.status == 'started' for r in state.runs.values()):
                console.line('\nPaused — 취소되었거나 결과가 확정되지 않은 실행이 있습니다.')
                if view['status'] == 'cancelled':
                    latest = next((r for r in reversed(list(state.runs.values()))
                                   if r.session_id == sid), None)
                    if latest is not None and latest.status == 'cancelled':
                        _run_status(console, latest)
                console.line('Resume은 기록을 복구하며 모델을 자동 재호출하지 않습니다.')
                if console.choose('Resume', 'Save & Exit') == 2:
                    raise _Exit()
                interrupted = [r.id for r in state.runs.values() if r.status == 'started']
                service.resume(sid)
                recovered = service.state()
                for identity in interrupted:
                    _run_status(console, recovered.runs[identity], recovered=True)
                console.line('Resumed — 저장된 초안에서 이어갑니다.')
                continue
            if view['outstanding_questions']:
                question = view['outstanding_questions'][0]
                index = next(i for i, q in enumerate(view['questions'], 1) if q['qid'] == question['qid'])
                console.head(f"Question {index} / {len(view['questions'])}")
                # question_rationale(배치 단위 생성 이유)은 질문마다 반복 노출돼
                # 혼란을 줬음(사용자 피드백 2026-10-10) — 저장은 유지, 표시만 생략.
                console.line(console.bold(question['text']))
                service.answer(sid, question['qid'], console.text('답변 > '))
                console.line('Saved')
                continue
            proposal = view['pending_proposal']
            if proposal is not None:
                _frame(console, proposal['frame'])
                choice = console.choose('Accept — 승인', 'Reject — 거부', 'Save & Exit — 저장 후 종료')
                if choice == 3:
                    raise _Exit()
                if choice == 1:
                    service.accept(sid, proposal['id'])
                else:
                    reason = console.text('어떤 점을 바꾸고 싶나요? > ')
                    service.reject(sid, proposal['id'], reason)
                    console.line('Rejected — 이전 제안은 이력에 남습니다.')
                continue
            regenerate = bool(view['proposals'])
            console.line('\n다시 생성하려면 명시적으로 선택해 주세요.' if regenerate else
                         '\n저장된 답변을 바탕으로 다음 질문 또는 프레임을 생성할 수 있습니다.')
            if console.choose('Regenerate' if regenerate else 'Generate', 'Save & Exit') == 2:
                raise _Exit()
            console.line('Preparing generation… (API 사용료가 발생할 수 있습니다.)')
            try:
                service.advance(sid, adapter_factory=adapter_factory, regenerate=regenerate,
                                max_output_tokens=max_output_tokens, timeout=timeout)
            except ValueError as error:
                console.line('Error: ' + str(error))
                console.line('자동 재시도하지 않습니다. 설정/기록을 확인한 뒤 다시 선택하거나 종료하세요.')
    except (_Exit, EOFError, KeyboardInterrupt):
        console.line('\nExit — 이미 제출해 저장된 내용은 유지됩니다. 같은 명령으로 다시 시작하세요.')
