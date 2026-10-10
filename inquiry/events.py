"""Strict version-one event validation; no file or network side effects."""
from copy import deepcopy
from datetime import datetime, timedelta
import math
import re
from .adapter import RunRequest, RunSignal, validate_request, validate_signal, validate_usage


class EventValidationError(ValueError):
    """An input is not a supported, serializable event."""


ENVELOPE_FIELDS = frozenset({
    'schema_version', 'event_id', 'seq', 'inquiry_id', 'actor', 'at', 'type', 'changes',
})
CHANGE_FIELDS = {
    'OperationProposed': frozenset({'kind', 'proposal_id', 'run_id', 'operation', 'target_ids', 'target_snapshot', 'output'}),
    'OperationRejected': frozenset({'kind', 'proposal_id', 'reason'}),
    'OperationAccepted': frozenset({'kind', 'proposal_id', 'result_id'}),
    'HypothesisRefined': frozenset({'kind', 'proposal_id', 'hypothesis_id', 'assumptions', 'falsified_if', 'reason'}),
    'ReviewNoteCreated': frozenset({'kind', 'note_id', 'proposal_id', 'hypothesis_id', 'objections'}),
    'BranchProposed': frozenset({'kind', 'proposal_id', 'run_id', 'parent_id', 'parent_snapshot', 'candidates'}),
    'BranchRejected': frozenset({'kind', 'proposal_id', 'reason'}),
    'BranchAccepted': frozenset({'kind', 'proposal_id', 'selected_ids', 'hypothesis_ids'}),
    'FramingStarted': frozenset({'kind', 'session_id', 'seed'}),
    'FramingControlRecorded': frozenset({'kind', 'session_id', 'run_id', 'control', 'answered_qids'}),
    'QuestionsIssued': frozenset({'kind', 'session_id', 'run_id', 'batch_id', 'questions'}),
    'AnswerRecorded': frozenset({'kind', 'session_id', 'qid', 'answer'}),
    'FrameProposed': frozenset({'kind', 'session_id', 'proposal_id', 'run_id', 'frame', 'qa'}),
    'FramingCancelled': frozenset({'kind', 'session_id', 'reason'}),
    'FramingResumed': frozenset({'kind', 'session_id', 'reason'}),
    'FrameRejected': frozenset({'kind', 'session_id', 'proposal_id', 'reason'}),
    'FrameAccepted': frozenset({'kind', 'session_id', 'proposal_id', 'inquiry_id', 'hypothesis_ids'}),
    'InquiryCreated': frozenset({'kind', 'seed', 'frame'}),
    'HypothesisCreated': frozenset({'kind', 'hypothesis_id', 'title', 'claim', 'parent_ids', 'assumptions', 'falsified_if'}),
    'EvidenceCreated': frozenset({'kind', 'evidence_id', 'type', 'content', 'uri', 'retrieved_at', 'actor'}),
    'EvidenceLinked': frozenset({'kind', 'evidence_id', 'hypothesis_id', 'relation'}),
    'HypothesisStateChanged': frozenset({'kind', 'hypothesis_id', 'from', 'to', 'trigger', 'actor', 'at', 'reason',
                                       'evidence_ids', 'evidence_snapshot', 'reopen_if', 'synthesis_target'}),
    'ActionCreated': frozenset({'kind', 'action_id', 'hypothesis_id', 'title'}),
    'ActionChecked': frozenset({'kind', 'action_id'}),
    'ActionUnchecked': frozenset({'kind', 'action_id'}),
    'RunStarted': frozenset({'kind', 'run_id', 'operation', 'model', 'target_ids', 'session_id', 'max_output_tokens', 'timeout'}),
    'RunDispatched': frozenset({'kind', 'run_id'}),
    'RunProgress': frozenset({'kind', 'run_id', 'text', 'provider_request_id'}),
    'RunHeartbeat': frozenset({'kind', 'run_id', 'provider_request_id'}),
    'RunUsageReported': frozenset({'kind', 'run_id', 'usage', 'provider_request_id'}),
    'RunSucceeded': frozenset({'kind', 'run_id', 'proposal', 'usage', 'provider_request_id'}),
    'RunFailed': frozenset({'kind', 'run_id', 'reason', 'provider_outcome', 'usage', 'provider_request_id'}),
    'RunCancelled': frozenset({'kind', 'run_id', 'reason', 'provider_outcome', 'usage', 'provider_request_id'}),
}
EVIDENCE_TYPES = frozenset({'external-article', 'measured-result', 'human-interview', 'human-judgment', 'dataset'})
UTC_TIMESTAMP = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$')


def _json_value(value):
    if value is None or type(value) in (bool, int):
        return
    if type(value) is str:
        try:
            value.encode('utf-8')
        except UnicodeEncodeError as error:
            raise EventValidationError('Text must be valid UTF-8.') from error
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise EventValidationError('JSON numbers must be finite.')
        return
    if type(value) is list:
        for item in value:
            _json_value(item)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise EventValidationError('JSON object keys must be strings.')
            _json_value(key)
            _json_value(item)
        return
    raise EventValidationError('Only JSON values are supported.')


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise EventValidationError(f'{field} must be a nonempty string.')


def _strings(value, field):
    if not isinstance(value, list):
        raise EventValidationError(f'{field} must be an array.')
    for item in value:
        _text(item, field)


def _timestamp(value, field):
    _text(value, field)
    if not UTC_TIMESTAMP.fullmatch(value):
        raise EventValidationError(f'{field} must be an ISO-8601 UTC timestamp.')
    try:
        moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if moment.utcoffset() != timedelta(0):
            raise ValueError('Not UTC')
    except ValueError as error:
        raise EventValidationError(f'{field} must be a valid UTC timestamp.') from error


def validate_event(event):
    """Return a detached event, rejecting unknown versions, kinds and fields.

    Domain operations must have explicit schemas before they can be stored.
    The frame is an opaque JSON object here; Framing's eight-field contract belongs
    to its proposal validation in M2-3.
    """
    try:
        _json_value(event)
    except RecursionError as error:
        raise EventValidationError('Cyclic or excessively nested JSON is unsupported.') from error
    if not isinstance(event, dict) or set(event) != ENVELOPE_FIELDS:
        raise EventValidationError('Event fields do not match schema version 1.')
    if type(event['schema_version']) is not int or event['schema_version'] != 1:
        raise EventValidationError('Unsupported schema_version.')
    if type(event['seq']) is not int or event['seq'] < 1:
        raise EventValidationError('seq must be a positive integer.')
    for field in ('event_id', 'inquiry_id', 'actor', 'at'):
        _text(event[field], field)
    _timestamp(event['at'], 'at')
    if event['type'] != 'changes-committed':
        raise EventValidationError('Unsupported event type.')
    changes = event['changes']
    if not isinstance(changes, list) or not changes:
        raise EventValidationError('changes must be a nonempty array.')
    for change in changes:
        if not isinstance(change, dict) or not isinstance(change.get('kind'), str):
            raise EventValidationError('Each change must have a string kind.')
        kind = change['kind']
        if kind not in CHANGE_FIELDS or set(change) != CHANGE_FIELDS[kind]:
            raise EventValidationError('Unsupported change kind or fields.')
        if kind.startswith('Run'):
            _text(change['run_id'], 'run_id')
            try:
                if kind == 'RunStarted':
                    validate_request(RunRequest(inquiry_id=event['inquiry_id'], context={},
                                                **{key: value for key, value in change.items() if key != 'kind'}))
                else:
                    provider = change.get('provider_request_id')
                    if provider is not None:
                        _text(provider, 'provider_request_id')
                    if 'usage' in change:
                        validate_usage(change['usage'])
                    if kind in ('RunProgress', 'RunHeartbeat', 'RunSucceeded'):
                        signal_kind = {'RunProgress': 'progress', 'RunHeartbeat': 'heartbeat', 'RunSucceeded': 'succeeded'}[kind]
                        validate_signal(RunSignal(signal_kind, text=change.get('text'), proposal=change.get('proposal'),
                                                  usage=change.get('usage'), provider_request_id=provider))
                    elif kind == 'RunUsageReported' and change['usage']['status'] != 'known':
                        raise ValueError('Reported usage must be known.')
                    elif kind in ('RunFailed', 'RunCancelled'):
                        _text(change['reason'], 'reason')
                        if change['provider_outcome'] not in ('unknown', 'failed', 'cancelled', 'succeeded', 'not-started'):
                            raise ValueError('Invalid provider outcome.')
            except ValueError as error:
                raise EventValidationError(str(error)) from error
        elif kind in ('OperationProposed', 'OperationRejected', 'OperationAccepted',
                      'HypothesisRefined', 'ReviewNoteCreated'):
            if kind == 'OperationProposed':
                for key in ('proposal_id', 'run_id', 'operation'):
                    _text(change[key], key)
                _strings(change['target_ids'], 'target_ids')
                if not isinstance(change['target_snapshot'], dict) or not isinstance(change['output'], dict):
                    raise EventValidationError('Invalid operation snapshot or output.')
            elif kind == 'OperationRejected':
                _text(change['proposal_id'], 'proposal_id')
                _text(change['reason'], 'reason')
            elif kind == 'OperationAccepted':
                _text(change['proposal_id'], 'proposal_id')
                _text(change['result_id'], 'result_id')
            elif kind == 'HypothesisRefined':
                for key in ('proposal_id', 'hypothesis_id', 'reason'):
                    _text(change[key], key)
                _strings(change['assumptions'], 'assumptions')
                _strings(change['falsified_if'], 'falsified_if')
            elif kind == 'ReviewNoteCreated':
                for key in ('note_id', 'proposal_id', 'hypothesis_id'):
                    _text(change[key], key)
                if not isinstance(change['objections'], list):
                    raise EventValidationError('objections must be an array.')
        elif kind in ('BranchProposed', 'BranchRejected', 'BranchAccepted'):
            _text(change['proposal_id'], 'proposal_id')
            if kind == 'BranchProposed':
                for key in ('run_id', 'parent_id'):
                    _text(change[key], key)
                if not isinstance(change['parent_snapshot'], dict) or not isinstance(change['candidates'], list):
                    raise EventValidationError('Invalid branch snapshot or candidates.')
            elif kind == 'BranchRejected':
                _text(change['reason'], 'reason')
            else:
                _strings(change['selected_ids'], 'selected_ids')
                if not isinstance(change['hypothesis_ids'], dict):
                    raise EventValidationError('hypothesis_ids must be an object.')
                for candidate, identity in change['hypothesis_ids'].items():
                    _text(candidate, 'candidate_id')
                    _text(identity, 'hypothesis_id')
        elif kind in ('FramingControlRecorded', 'QuestionsIssued', 'AnswerRecorded', 'FrameProposed',
                      'FramingCancelled', 'FramingResumed', 'FrameRejected', 'FrameAccepted'):
            for key in ('session_id', 'run_id', 'batch_id', 'qid', 'answer', 'proposal_id', 'reason', 'inquiry_id'):
                if key in change:
                    _text(change[key], key)
            if kind == 'FramingControlRecorded':
                if not isinstance(change['control'], dict):
                    raise EventValidationError('control must be an object.')
                _strings(change['answered_qids'], 'answered_qids')
            elif kind == 'QuestionsIssued':
                if not isinstance(change['questions'], list) or not change['questions']:
                    raise EventValidationError('questions must be a nonempty array.')
                for question in change['questions']:
                    if not isinstance(question, dict) or set(question) != {'qid', 'text'}:
                        raise EventValidationError('Invalid persisted question.')
                    for key in ('qid', 'text'):
                        _text(question[key], key)
            elif kind == 'FrameProposed':
                if not isinstance(change['frame'], dict) or not isinstance(change['qa'], list):
                    raise EventValidationError('Invalid frame or QA.')
                for qa in change['qa']:
                    if not isinstance(qa, dict) or set(qa) != {'qid', 'question', 'answer'}:
                        raise EventValidationError('Invalid QA record.')
                    for key in qa:
                        _text(qa[key], key)
            elif kind == 'FrameAccepted':
                if not isinstance(change['hypothesis_ids'], dict):
                    raise EventValidationError('hypothesis_ids must be an object.')
                for candidate, identity in change['hypothesis_ids'].items():
                    _text(candidate, 'candidate_id')
                    _text(identity, 'hypothesis_id')
        elif kind in ('FramingStarted', 'InquiryCreated'):
            _text(change['seed'], 'seed')
            if kind == 'FramingStarted':
                _text(change['session_id'], 'session_id')
            elif not isinstance(change['frame'], dict):
                raise EventValidationError('frame must be a JSON object.')
        elif kind == 'HypothesisCreated':
            for key in ('hypothesis_id', 'title', 'claim'):
                _text(change[key], key)
            for key in ('parent_ids', 'assumptions', 'falsified_if'):
                _strings(change[key], key)
        elif kind == 'EvidenceCreated':
            for key in ('evidence_id', 'type', 'content', 'actor'):
                _text(change[key], key)
            if change['type'] not in EVIDENCE_TYPES:
                raise EventValidationError('Unsupported evidence type; model opinions are not evidence.')
            _timestamp(change['retrieved_at'], 'retrieved_at')
            if change['uri'] is not None:
                _text(change['uri'], 'uri')
            if change['type'] in ('external-article', 'dataset') and not change['uri']:
                raise EventValidationError('External articles and datasets require a source URI.')
        elif kind == 'ActionCreated':
            for key in ('action_id', 'hypothesis_id', 'title'):
                _text(change[key], key)
        elif kind in ('ActionChecked', 'ActionUnchecked'):
            _text(change['action_id'], 'action_id')
        elif kind == 'EvidenceLinked':
            for key in ('evidence_id', 'hypothesis_id'):
                _text(change[key], key)
            if change['relation'] not in ('supports', 'challenges'):
                raise EventValidationError('Invalid evidence relation.')
        elif kind == 'HypothesisStateChanged':
            for key in ('hypothesis_id', 'from', 'to', 'trigger', 'actor', 'reason'):
                _text(change[key], key)
            _timestamp(change['at'], 'at')
            _strings(change['evidence_ids'], 'evidence_ids')
            if len(set(change['evidence_ids'])) != len(change['evidence_ids']):
                raise EventValidationError('Duplicate evidence references.')
            for key in ('reopen_if', 'synthesis_target'):
                if change[key] is not None:
                    _text(change[key], key)
            snapshot = change['evidence_snapshot']
            if snapshot is not None:
                if not isinstance(snapshot, dict) or set(snapshot) != {'items', 'note'} or not isinstance(snapshot['items'], list):
                    raise EventValidationError('Invalid evidence snapshot.')
                _text(snapshot['note'], 'snapshot note')
    return deepcopy(event)
