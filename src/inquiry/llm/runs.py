"""Durable single-run orchestration with explicit recovery; no provider SDK."""
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import time
from uuid import uuid4

from inquiry.llm.adapter import validate_request, validate_signal, validate_usage, unknown_usage, not_started_usage
from inquiry.domain.replay import replay
from inquiry.store.store import Store


class Runner:
    def __init__(self, root, *, clock=time.monotonic):
        self.root = Path(root).resolve()
        self.clock = clock
        self.cleanup_errors = {}

    def state(self):
        return replay(Store(self.root).read_all())

    def get(self, run_id):
        run = self.state().runs.get(run_id)
        if run is None:
            raise ValueError('Run does not exist.')
        return run

    def totals(self):
        runs = self.state().runs.values()
        inputs, outputs, unknown = 0, 0, 0
        for run in runs:
            if run.usage['status'] == 'unknown':
                unknown += 1
            else:
                inputs += run.usage['input_tokens']
                outputs += run.usage['output_tokens']
        return dict(input_tokens=inputs, output_tokens=outputs, unknown_runs=unknown)

    def _record(self, store, inquiry_id, change, actor='agent:runner', *, extra_changes=()):
        history = store.read_all()
        record = dict(schema_version=1, event_id=uuid4().hex, seq=len(history) + 1,
                      inquiry_id=inquiry_id, actor=actor, at=datetime.now(timezone.utc).isoformat(),
                      type='changes-committed', changes=[change, *extra_changes])
        store.append(record, expected_seq=len(history))
        return replay(store.read_all()).runs[change['run_id']]

    def _finish(self, store, request, kind, *, reason=None, outcome='unknown', proposal=None,
                usage=None, provider_request_id=None, extra_changes=(), cancellation_changes=None):
        state = replay(store.read_all())
        current = state.runs[request.run_id]
        if kind == 'RunCancelled' and cancellation_changes is not None:
            extra_changes = cancellation_changes(state, request, reason)
            if not isinstance(extra_changes, list) or any(
                not isinstance(change, dict) or change.get('kind') != 'FramingCancelled'
                for change in extra_changes
            ):
                raise ValueError('Only draft cancellation may accompany RunCancelled.')
        change = dict(kind=kind, run_id=request.run_id, usage=usage or current.usage,
                      provider_request_id=provider_request_id or current.provider_request_id)
        if kind == 'RunSucceeded':
            change['proposal'] = proposal
        else:
            change.update(reason=reason, provider_outcome=outcome)
        return self._record(store, request.inquiry_id, change, extra_changes=extra_changes)

    @staticmethod
    def _signal_metadata(current, signal):
        provider = signal.provider_request_id or current.provider_request_id
        if current.provider_request_id is not None and provider != current.provider_request_id:
            raise ValueError('Provider request identity mismatch.')
        usage = current.usage
        if signal.usage is not None and signal.usage['status'] == 'known':
            if usage['status'] == 'known' and usage != signal.usage:
                raise ValueError('Conflicting final usage.')
            usage = signal.usage
        return usage, provider

    def execute(self, request, adapter, *, cancelled=None, preflight=None, success_changes=None,
                cancellation_changes=None):
        """Run once and return only persisted outcomes.

        Cancellation/timeout are checked between signals. Adapter I/O must itself
        honor timeout; Python cannot forcibly stop arbitrary blocking iterators.
        Store errors and process-ending BaseExceptions propagate, preserving an
        unfinished/uncertain record for explicit recover(), never a blind retry.

        Application-owned hooks run under the writer lock. preflight rejects stale
        application state before dispatch; success_changes validates a proposal
        and returns draft-only changes to save atomically with RunSucceeded. Hooks
        are not model-supplied code and cannot approve domain changes. The
        cancellation_changes hook binds draft cancellation to RunCancelled in
        the same durable event, including cancellation before dispatch.
        """
        request = validate_request(request)
        cancelled = cancelled or (lambda: False)
        with Store(self.root) as store:
            state = replay(store.read_all())
            if state.inquiry_id not in (None, request.inquiry_id):
                raise ValueError('Request belongs to another inquiry.')
            if request.run_id in state.runs:
                raise ValueError('Run ID already exists; inspect its outcome, do not dispatch again.')
            if any(run.status == 'started' for run in state.runs.values()):
                raise ValueError('Unfinished runs require explicit recovery.')
            if preflight is not None:
                preflight(state)
            started = asdict(request)
            started.pop('context')  # Never persist request context or provider credentials.
            started.pop('inquiry_id')
            started['target_ids'] = list(request.target_ids)
            started['kind'] = 'RunStarted'
            self._record(store, request.inquiry_id, started)
            if cancelled():
                return self._finish(store, request, 'RunCancelled', reason='cancelled-before-dispatch',
                                    outcome='not-started', usage=not_started_usage(),
                                    cancellation_changes=cancellation_changes)
            deadline = self.clock() + request.timeout
            def stop_reason():
                if cancelled():
                    return 'cancelled'
                if self.clock() >= deadline:
                    return 'timeout'
                return None
            self._record(store, request.inquiry_id, dict(kind='RunDispatched', run_id=request.run_id))
            try:
                stream = iter(adapter.run(request))
            except Exception as error:
                return self._finish(store, request, 'RunFailed', reason='adapter-error:' + type(error).__name__)
            try:
                while True:
                    reason = stop_reason()
                    if reason:
                        return self._finish(store, request, 'RunCancelled', reason=reason,
                                            cancellation_changes=cancellation_changes)
                    try:
                        raw = next(stream)
                    except StopIteration:
                        return self._finish(store, request, 'RunFailed', reason='missing-terminal-signal')
                    except KeyboardInterrupt:
                        return self._finish(store, request, 'RunCancelled', reason='keyboard-interrupt',
                                            cancellation_changes=cancellation_changes)
                    except Exception as error:
                        return self._finish(store, request, 'RunFailed', reason='adapter-error:' + type(error).__name__)
                    current = replay(store.read_all()).runs[request.run_id]
                    try:
                        signal = validate_signal(raw)
                        usage, provider = self._signal_metadata(current, signal)
                    except ValueError:
                        return self._finish(store, request, 'RunFailed', reason='invalid-adapter-signal')
                    reason = stop_reason()
                    if reason:
                        outcome = signal.kind if signal.kind in ('succeeded', 'failed', 'cancelled') else 'unknown'
                        return self._finish(store, request, 'RunCancelled', reason=reason, outcome=outcome,
                                            usage=usage, provider_request_id=provider,
                                            cancellation_changes=cancellation_changes)
                    if signal.kind == 'succeeded':
                        try:
                            extras = [] if success_changes is None else success_changes(
                                replay(store.read_all()), request, signal.proposal)
                            allowed = {'FramingControlRecorded', 'QuestionsIssued', 'FrameProposed',
                                       'BranchProposed', 'OperationProposed'}
                            if not isinstance(extras, list) or any(
                                not isinstance(change, dict) or change.get('kind') not in allowed
                                for change in extras
                            ):
                                raise ValueError('Only proposal draft changes may accompany success.')
                            return self._finish(store, request, 'RunSucceeded', proposal=signal.proposal,
                                                usage=usage, provider_request_id=provider, extra_changes=extras)
                        except ValueError:
                            # Schema/replay rejection happens before append. I/O
                            # errors and process exits are deliberately not caught.
                            return self._finish(store, request, 'RunFailed', reason='invalid-proposal',
                                                outcome='succeeded', usage=usage, provider_request_id=provider)
                    if signal.kind in ('failed', 'cancelled'):
                        return self._finish(store, request, 'RunFailed' if signal.kind == 'failed' else 'RunCancelled',
                                            reason=signal.reason, outcome=signal.kind, usage=usage,
                                            provider_request_id=provider, cancellation_changes=cancellation_changes)
                    if signal.kind == 'usage':
                        if current.usage == usage and current.provider_request_id == provider:
                            continue
                        change = dict(kind='RunUsageReported', run_id=request.run_id,
                                      usage=usage, provider_request_id=provider)
                    else:
                        change = dict(kind='RunProgress' if signal.kind == 'progress' else 'RunHeartbeat',
                                      run_id=request.run_id, provider_request_id=provider)
                        if signal.kind == 'progress':
                            change['text'] = signal.text
                    self._record(store, request.inquiry_id, change)
            finally:
                try:
                    close = getattr(stream, 'close', None)
                    if close is not None:
                        close()
                except Exception as error:
                    # Cleanup must not replace a durable outcome or primary error.
                    self.cleanup_errors[request.run_id] = type(error).__name__

    def recover(self):
        """Explicitly fail interrupted runs, without invoking any adapter."""
        # A missing project is a read-only no-op, not a request to initialize one.
        if not any(run.status == 'started' for run in self.state().runs.values()):
            return []
        recovered = []
        with Store(self.root) as store:
            state = replay(store.read_all())
            for run in state.runs.values():
                if run.status == 'started':
                    self._record(store, state.inquiry_id, dict(kind='RunFailed', run_id=run.id,
                        reason='process-interrupted', provider_outcome='unknown', usage=run.usage,
                        provider_request_id=run.provider_request_id), actor='system:recovery')
                    recovered.append(run.id)
        return recovered

    def report_usage(self, run_id, usage, *, provider_request_id=None):
        usage = validate_usage(usage)
        if usage['status'] != 'known':
            raise ValueError('Only known final usage may be reported.')
        if provider_request_id is not None and (not isinstance(provider_request_id, str) or not provider_request_id.strip()):
            raise ValueError('Invalid provider request ID.')
        with Store(self.root) as store:
            state = replay(store.read_all())
            run = state.runs.get(run_id)
            if run is None:
                raise ValueError('Run does not exist.')
            if provider_request_id is not None and run.provider_request_id not in (None, provider_request_id):
                raise ValueError('Provider request identity mismatch.')
            if run.usage == usage and provider_request_id in (None, run.provider_request_id):
                return run
            return self._record(store, state.inquiry_id, dict(kind='RunUsageReported', run_id=run_id,
                                usage=usage, provider_request_id=provider_request_id or run.provider_request_id))
