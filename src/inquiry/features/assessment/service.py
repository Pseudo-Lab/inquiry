"""ADR-D3 scoring runs: a dedicated one-step path, not the operation approval flow.

A scoring run (`hypothesis.assess` / `hypothesis.reassess`) returns an agent-estimate
that the Runner records atomically with RunSucceeded as `HypothesisAssessed` /
`ConfidenceUpdated` under `agent:runner`. There is no human OperationAccepted step:
the estimate is recorded, not "confirmed" (source stays agent-estimate, principle 3),
and it triggers no state transition.
"""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from inquiry.llm.adapter import RunRequest, _number, _string
from inquiry.features.branch.schema import parent_snapshot
from inquiry.features.assessment.prompts import (
    ASSESS_SYSTEM, REASSESS_SYSTEM, INITIAL_OUTPUT_SCHEMA, SINGLE_AXIS_OUTPUT_SCHEMA)
from inquiry.features.assessment.schema import validate_axis, validate_initial_output
from inquiry.domain.replay import replay
from inquiry.llm.runs import Runner
from inquiry.store.store import Store


class AssessmentService:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def state(self):
        return replay(Store(self.root).read_all())

    def assessment(self, hypothesis_id):
        state = self.state()
        if hypothesis_id not in state.hypotheses:
            raise ValueError('Hypothesis does not exist.')
        return state.hypotheses[hypothesis_id].assessment

    @staticmethod
    def _linked_evidence(state, hypothesis_id):
        """Evidence linked to this hypothesis, shaped for the scoring prompt (id enables citing)."""
        items = []
        for link in state.evidence_links:
            if link.hypothesis_id == hypothesis_id and link.evidence_id in state.evidence:
                ev = state.evidence[link.evidence_id]
                items.append(dict(id=ev.id, type=ev.type, relation=link.relation,
                                  content=ev.content, uri=ev.uri, retrieved_at=ev.retrieved_at))
        return items

    def _score(self, hypothesis_id, operation, system, output_schema, build_changes,
               adapter, adapter_factory, model, max_output_tokens, timeout, cancelled,
               include_evidence=False):
        _string(hypothesis_id)
        if adapter is not None and adapter_factory is not None:
            raise ValueError('Provide either adapter or adapter_factory, not both.')
        if type(max_output_tokens) is not int or max_output_tokens <= 0:
            raise ValueError('Expected positive integer max_output_tokens.')
        if not _number(timeout) or timeout <= 0:
            raise ValueError('Expected positive finite timeout.')
        state = self.state()
        if state.inquiry is None:
            raise ValueError('Accept a framing proposal or initialize an inquiry first.')
        node = state.hypotheses.get(hypothesis_id)
        if node is None:
            raise ValueError('Hypothesis does not exist.')
        if any(run.status == 'started' for run in state.runs.values()):
            raise ValueError('Unfinished runs require explicit recovery.')
        if adapter_factory is not None:
            binding = adapter_factory()
            if not isinstance(binding, tuple) or len(binding) != 2:
                raise ValueError('Adapter factory must return (adapter, model).')
            adapter, model = binding
        if adapter is None:
            raise ValueError('No assessment adapter configured.')
        context = dict(system=system, output_schema=output_schema,
                       inquiry_frame=deepcopy(state.inquiry.frame),
                       hypothesis=parent_snapshot(node))
        if include_evidence:
            context['evidence'] = self._linked_evidence(state, hypothesis_id)
        request = RunRequest(inquiry_id=state.inquiry_id, run_id='R-' + uuid4().hex,
            operation=operation, model=model, target_ids=(hypothesis_id,), session_id=None,
            max_output_tokens=max_output_tokens, timeout=timeout, context=context)

        def preflight(current):
            if current.inquiry_id != state.inquiry_id or hypothesis_id not in current.hypotheses:
                raise ValueError('Assessment target changed; reload its saved state.')

        def success(current, actual_request, output):
            preflight(current)
            return build_changes(actual_request.run_id, output)

        run = Runner(self.root).execute(request, adapter, cancelled=cancelled,
                                        preflight=preflight, success_changes=success)
        if run.status != 'succeeded':
            raise ValueError(f'Assessment run {run.id} {run.status}: {run.reason}. '
                             'Inspect saved state before another explicit generation.')
        return self.assessment(hypothesis_id)

    def assess(self, hypothesis_id, adapter=None, *, adapter_factory=None, model='fake',
               max_output_tokens=4000, timeout=60.0, cancelled=None):
        """Initial four-axis agent-estimate at `suggested` (evidence_strength stays null)."""
        def build(run_id, output):
            snapshot = validate_initial_output(output)
            return [dict(kind='HypothesisAssessed', hypothesis_id=hypothesis_id,
                         run_id=run_id, assessment=snapshot)]
        return self._score(hypothesis_id, 'hypothesis.assess', ASSESS_SYSTEM,
                           INITIAL_OUTPUT_SCHEMA, build, adapter, adapter_factory, model,
                           max_output_tokens, timeout, cancelled)

    def update_confidence(self, hypothesis_id, adapter=None, *, adapter_factory=None, model='fake',
                          max_output_tokens=4000, timeout=60.0, cancelled=None):
        """Re-score evidence_strength from linked evidence during exploring."""
        def build(run_id, output):
            score = validate_axis(output)
            if score is None:
                raise ValueError('Confidence update requires a scored axis.')
            return [dict(kind='ConfidenceUpdated', hypothesis_id=hypothesis_id,
                         run_id=run_id, axis='evidence_strength', score=score)]
        return self._score(hypothesis_id, 'hypothesis.reassess', REASSESS_SYSTEM,
                           SINGLE_AXIS_OUTPUT_SCHEMA, build, adapter, adapter_factory, model,
                           max_output_tokens, timeout, cancelled, include_evidence=True)
