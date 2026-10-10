"""Bounded, lazy OpenAI Responses adapter.

The provider SDK is deliberately imported only for production construction;
tests can supply a small factory and completely offline event stream.
"""
import json
import logging
import math
import os
import re
import time
from contextlib import contextmanager

from inquiry.llm.adapter import RunSignal, _object, unknown_usage, validate_request


_BASE_URL = 'https://api.openai.com/v1'
_PROGRESS_CHARS = 1024
_PROGRESS_SECONDS = 1.0
_DROP_SCHEMA_KEYS = frozenset(('default', 'examples', 'title', '$schema', 'uniqueItems'))
_IGNORED_EVENTS = frozenset((
    'response.created', 'response.in_progress', 'response.output_item.added',
    'response.output_item.done', 'response.content_part.added',
    'response.content_part.done', 'response.output_text.done',
    'response.output_text.annotation.added', 'response.reasoning.delta',
    'response.reasoning.done', 'response.reasoning_summary_part.added',
    'response.reasoning_summary_part.done', 'response.reasoning_summary_text.delta',
    'response.reasoning_summary_text.done', 'response.reasoning_text.delta',
    'response.reasoning_text.done', 'response.queued',
))
_REQUEST_ID = re.compile(r'^[A-Za-z0-9._-]{1,200}$')
CUSTOM_HEADERS_FORBIDDEN = ('OpenAI custom headers (OPENAI_CUSTOM_HEADERS) are not supported; '
                            'remove that environment setting before generation.')


def _guard_custom_headers():
    if os.environ.get('OPENAI_CUSTOM_HEADERS', '').strip():
        raise ValueError(CUSTOM_HEADERS_FORBIDDEN)


def _value(item, name, default=None):
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError('non-finite JSON value')


def _strict_json(text):
    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError('non-finite JSON value')
        return result
    value = json.loads(text, object_pairs_hook=_strict_pairs,
                       parse_constant=_reject_constant, parse_float=finite_float)
    if type(value) is not dict or not value:
        raise ValueError('expected JSON object')
    return _object(value)


def _server_schema(value, names=False):
    """Copy the local schema while excluding metadata unsupported by Responses."""
    if isinstance(value, list):
        return [_server_schema(item, names) for item in value]
    if not isinstance(value, dict):
        return value
    return {key: _server_schema(item, key in ('properties', '$defs', 'definitions'))
            for key, item in value.items() if names or key not in _DROP_SCHEMA_KEYS}


def _usage(response):
    raw = _value(response, 'usage')
    inputs = _value(raw, 'input_tokens')
    outputs = _value(raw, 'output_tokens')
    if type(inputs) is not int or type(outputs) is not int or inputs < 0 or outputs < 0:
        return unknown_usage()
    return dict(status='known', input_tokens=inputs, output_tokens=outputs,
                est_cost=None, price_ref=None)


def _request_id(stream, secret):
    response = _value(stream, 'response')
    headers = _value(response, 'headers', {})
    if hasattr(headers, 'get'):
        value = headers.get('x-request-id')
        if isinstance(value, str) and _REQUEST_ID.fullmatch(value) and secret not in value:
            return value
    return None


def _final_text(response):
    outputs = _value(response, 'output')
    if not isinstance(outputs, (tuple, list)):
        raise ValueError('missing output')
    texts = []
    for output in outputs:
        output_type = _value(output, 'type')
        if output_type == 'reasoning':
            continue
        if output_type != 'message':
            raise ValueError('unsupported output')
        content = _value(output, 'content')
        if not isinstance(content, (tuple, list)):
            raise ValueError('missing content')
        for part in content:
            kind = _value(part, 'type')
            if kind == 'refusal':
                raise RuntimeError('refusal')
            if kind != 'output_text':
                raise ValueError('unsupported content')
            text = _value(part, 'text')
            if not isinstance(text, str):
                raise ValueError('invalid text')
            texts.append(text)
    if not texts:
        raise ValueError('missing output text')
    return ''.join(texts)


def _error_reason(error):
    return {
        'AuthenticationError': 'authentication-error',
        'RateLimitError': 'rate-limited',
        'APITimeoutError': 'timeout',
        'PermissionDeniedError': 'permission-denied',
        'APIConnectionError': 'connection-error',
        'ValueError': 'invalid-request',
    }.get(type(error).__name__, 'provider-error')


class _DiscardSDKLogs(logging.Filter):
    def filter(self, record):
        return not record.name.startswith('openai')


@contextmanager
def _suppress_sdk_logs():
    """Temporarily suppress only OpenAI records, including propagated children."""
    marker = _DiscardSDKLogs()
    handlers = []
    names = ['openai', 'openai._base_client'] + [name for name in logging.Logger.manager.loggerDict
                           if name.startswith('openai.')]
    loggers = []
    for name in names:
        logger = logging.getLogger(name)
        logger.addFilter(marker)
        loggers.append(logger)
        while logger is not None:
            for handler in logger.handlers:
                handler.addFilter(marker)
                handlers.append(handler)
            logger = logger.parent
    try:
        yield
    finally:
        for logger in loggers:
            logger.removeFilter(marker)
        for handler in handlers:
            handler.removeFilter(marker)


def _production_factory(**kwargs):
    import httpx
    from openai import OpenAI
    client = httpx.Client(trust_env=False, follow_redirects=False)
    try:
        return OpenAI(**kwargs, http_client=client)
    except BaseException:
        try:
            client.close()
        except Exception:
            pass
        raise


class OpenAIAdapter:
    """Translate a single Responses stream into provider-independent signals."""
    def __init__(self, settings, *, client_factory=None, clock=time.monotonic):
        _guard_custom_headers()
        self.settings = settings
        self.client_factory = client_factory or _production_factory
        self.clock = clock

    def _create(self, request):
        _guard_custom_headers()
        timeout = min(10.0, float(request.timeout))
        if request.operation not in (
                'framing.control', 'framing.propose', 'hypothesis.fork',
                'hypothesis.deepen', 'hypothesis.challenge', 'hypothesis.synthesize'):
            raise ValueError('unsupported operation')
        system, output_schema = request.context['system'], request.context['output_schema']
        if not isinstance(system, str) or not isinstance(output_schema, dict):
            raise ValueError('invalid context')
        if request.operation in ('hypothesis.fork', 'hypothesis.deepen', 'hypothesis.challenge',
                                 'hypothesis.synthesize'):
            from inquiry.features.branch.schema import parent_context
            frame = request.context['inquiry_frame']
            if not isinstance(frame, dict):
                raise ValueError('invalid branch context')
            if request.operation == 'hypothesis.fork':
                payload = dict(inquiry_frame=frame, parent=parent_context(request.context['parent']))
            else:
                parents = request.context['parents']
                if not isinstance(parents, (list, tuple)):
                    raise ValueError('invalid operation context')
                payload = dict(inquiry_frame=frame,
                               parents=[parent_context(parent) for parent in parents])
        else:
            payload = dict(seed=request.context.get('seed'), qa=request.context.get('qa', []))
            rejected = request.context.get('rejected')
            if rejected:
                payload['rejected'] = rejected
        schema = _server_schema(output_schema)
        # Empty explicit organization/project prevents SDK environment routing.
        client = None
        try:
            with _suppress_sdk_logs():
                client = self.client_factory(api_key=self.settings.api_key, base_url=_BASE_URL,
                                             max_retries=0, timeout=timeout,
                                             organization='', project='')
                stream = client.responses.create(
                    model=request.model, store=False, stream=True,
                    instructions=system,
                    input=json.dumps(payload, ensure_ascii=False, separators=(',', ':')),
                    max_output_tokens=request.max_output_tokens,
                    text=dict(format=dict(type='json_schema', name='inquiry_response', strict=True,
                                          schema=schema)),
                )
        except BaseException:
            close = getattr(client, 'close', None)
            if close is not None:
                try:
                    close()
                except Exception:
                    pass
            raise
        return client, stream

    def run(self, request):
        """Yield no proposal before a completed authoritative response."""
        request = validate_request(request)
        client = stream = None
        provider_request_id = None
        try:
            try:
                client, stream = self._create(request)
            except Exception as error:
                yield RunSignal('failed', reason=_error_reason(error), usage=unknown_usage())
                return
            provider_request_id = _request_id(stream, self.settings.api_key)
            refused = False
            pending = []
            pending_chars = 0
            last_progress = None
            for event in stream:
                event_type = _value(event, 'type')
                if event_type in _IGNORED_EVENTS:
                    continue
                if event_type == 'response.output_text.delta':
                    delta = _value(event, 'delta')
                    if isinstance(delta, str) and delta.strip():
                        pending.append(delta)
                        pending_chars += len(delta)
                        if (last_progress is None or pending_chars >= _PROGRESS_CHARS or
                                self.clock() - last_progress >= _PROGRESS_SECONDS):
                            yield RunSignal('progress', text=''.join(pending),
                                            provider_request_id=provider_request_id)
                            pending = []
                            pending_chars = 0
                            # Exclude the consumer's replay/fsync time from this interval.
                            last_progress = self.clock()
                    continue
                if event_type in ('response.refusal.delta', 'response.refusal.done'):
                    refused = True
                    continue
                response = _value(event, 'response')
                # Terminal response owns the complete output and usage. Do not put a
                # best-effort progress tail before it: a deadline could hide that usage.
                if event_type == 'response.completed':
                    usage = _usage(response)
                    try:
                        if refused:
                            raise RuntimeError('refusal')
                        proposal = _strict_json(_final_text(response))
                    except RuntimeError:
                        yield RunSignal('failed', reason='refusal', usage=usage,
                                        provider_request_id=provider_request_id)
                    except (TypeError, ValueError, json.JSONDecodeError):
                        yield RunSignal('failed', reason='invalid-response', usage=usage,
                                        provider_request_id=provider_request_id)
                    else:
                        yield RunSignal('succeeded', proposal=proposal, usage=usage,
                                        provider_request_id=provider_request_id)
                    return
                if event_type == 'response.incomplete':
                    yield RunSignal('failed', reason='incomplete', usage=_usage(response),
                                    provider_request_id=provider_request_id)
                    return
                if event_type == 'response.failed':
                    yield RunSignal('failed', reason='provider-error', usage=_usage(response),
                                    provider_request_id=provider_request_id)
                    return
                yield RunSignal('failed', reason='invalid-response', usage=unknown_usage(),
                                provider_request_id=provider_request_id)
                return
            yield RunSignal('failed', reason='refusal' if refused else 'missing-terminal-response',
                            usage=unknown_usage(),
                            provider_request_id=provider_request_id)
        except Exception as error:
            yield RunSignal('failed', reason=_error_reason(error), usage=unknown_usage(),
                            provider_request_id=provider_request_id)
        finally:
            for resource in (stream, client):
                close = getattr(resource, 'close', None)
                if close is not None:
                    try:
                        close()
                    except Exception:
                        pass
