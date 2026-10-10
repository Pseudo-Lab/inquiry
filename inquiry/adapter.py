"""Provider-independent run boundary; no SDK, persistence, or logging.

Adapters must honor request.timeout during blocking I/O. The runner checks its
deadline and cancellation between signals and closes the iterator; it cannot
preempt arbitrary blocking Python code.
"""

import math
from dataclasses import dataclass, replace
from typing import Iterator, Optional, Protocol


@dataclass(frozen=True)
class RunRequest:
    inquiry_id: str
    run_id: str
    operation: str
    model: str
    context: dict
    target_ids: tuple = ()
    session_id: Optional[str] = None
    max_output_tokens: int = 1000
    timeout: float = 30.0


@dataclass(frozen=True)
class RunSignal:
    kind: str
    text: Optional[str] = None
    proposal: Optional[dict] = None
    usage: Optional[dict] = None
    reason: Optional[str] = None
    provider_request_id: Optional[str] = None


class Adapter(Protocol):
    def run(self, request: RunRequest) -> Iterator[RunSignal]:
        """Yield signals with bounded I/O and release resources when closed."""
        ...


def _string(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('expected nonempty string')
    try:
        value.encode('utf-8')
    except UnicodeError:
        raise ValueError('expected UTF-8 string') from None


def _json_copy(value, active=None):
    """Validate and detach JSON without invoking arbitrary object serializers."""
    if active is None:
        active = set()
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) is str:
        value.encode('utf-8')
        return value
    if type(value) not in (list, dict) or id(value) in active:
        raise ValueError('expected finite JSON value')
    active.add(id(value))
    try:
        if isinstance(value, list):
            return [_json_copy(item, active) for item in value]
        result = {}
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError('expected string JSON keys')
            key.encode('utf-8')
            result[key] = _json_copy(item, active)
        return result
    finally:
        active.remove(id(value))


def _object(value):
    if type(value) is not dict:
        raise ValueError('expected JSON object')
    try:
        return _json_copy(value)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError('expected finite UTF-8 JSON object') from None


def _number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def validate_request(request):
    if not isinstance(request, RunRequest):
        raise ValueError('expected RunRequest')
    for value in (request.inquiry_id, request.run_id, request.operation, request.model):
        _string(value)
    if request.session_id is not None:
        _string(request.session_id)
    if not isinstance(request.target_ids, (list, tuple)):
        raise ValueError('expected target list or tuple')
    for target in request.target_ids:
        _string(target)
    targets = tuple(request.target_ids)
    if len(set(targets)) != len(targets):
        raise ValueError('expected unique targets')
    if type(request.max_output_tokens) is not int or request.max_output_tokens <= 0:
        raise ValueError('expected positive token limit')
    if not _number(request.timeout) or request.timeout <= 0:
        raise ValueError('expected positive finite timeout')
    return replace(request, context=_object(request.context), target_ids=targets)


def unknown_usage():
    return dict(status='unknown', input_tokens=None, output_tokens=None,
                est_cost=None, price_ref=None)


def not_started_usage():
    return dict(status='not-started', input_tokens=0, output_tokens=0,
                est_cost=None, price_ref=None)


def validate_usage(usage):
    if type(usage) is not dict or set(usage) != set(unknown_usage()):
        raise ValueError('invalid usage fields')
    status = usage['status']
    if status == 'unknown':
        if any(usage[key] is not None for key in usage if key != 'status'):
            raise ValueError('unknown usage must contain null values')
    elif status in ('known', 'not-started'):
        for key in ('input_tokens', 'output_tokens'):
            if type(usage[key]) is not int or usage[key] < 0:
                raise ValueError('expected nonnegative token counts')
        if status == 'not-started':
            if usage != not_started_usage():
                raise ValueError('invalid not-started usage')
        else:
            cost, price = usage['est_cost'], usage['price_ref']
            if price is not None:
                _string(price)
            if cost is not None:
                if not _number(cost) or cost < 0 or price is None:
                    raise ValueError('expected finite nonnegative cost with price reference')
    else:
        raise ValueError('unsupported usage status')
    return dict(usage)


def validate_signal(signal):
    if not isinstance(signal, RunSignal):
        raise ValueError('expected RunSignal')
    allowed = {
        'progress': {'text'}, 'heartbeat': set(), 'usage': {'usage'},
        'succeeded': {'proposal', 'usage'},
        'failed': {'reason', 'usage'}, 'cancelled': {'reason', 'usage'},
    }
    if not isinstance(signal.kind, str) or signal.kind not in allowed:
        raise ValueError('unsupported signal kind')
    for field in ('text', 'proposal', 'usage', 'reason'):
        if field not in allowed[signal.kind] and getattr(signal, field) is not None:
            raise ValueError('unsupported signal fields')
    if signal.provider_request_id is not None:
        _string(signal.provider_request_id)
    if signal.kind == 'progress':
        _string(signal.text)
    if signal.kind in ('failed', 'cancelled'):
        _string(signal.reason)
    proposal = None
    if signal.kind == 'succeeded':
        proposal = _object(signal.proposal)
        if not proposal:
            raise ValueError('expected nonempty proposal')
    usage = validate_usage(signal.usage) if signal.usage is not None else None
    if usage is not None and usage['status'] == 'not-started':
        raise ValueError('provider signal cannot report not-started usage')
    if signal.kind == 'usage' and (usage is None or usage['status'] != 'known'):
        raise ValueError('usage signal requires known usage')
    return replace(signal, proposal=proposal, usage=usage)
