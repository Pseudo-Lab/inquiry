import unittest
from dataclasses import FrozenInstanceError, replace

from inquiry.adapter import (RunRequest, RunSignal, not_started_usage,
                             unknown_usage, validate_request, validate_signal,
                             validate_usage)
from tests.fakes import FakeAdapter


def request(**changes):
    return replace(RunRequest('I-1', 'R-1', 'expand', 'fake', {}), **changes)


def known(**changes):
    value = dict(status='known', input_tokens=3, output_tokens=2,
                 est_cost=None, price_ref=None)
    value.update(changes)
    return value


class AdapterTests(unittest.TestCase):
    def test_request_is_frozen_and_detached(self):
        source = request(context={'nested': [1]}, target_ids=['N-1'])
        result = validate_request(source)
        source.context['nested'].append(2)
        self.assertEqual(result.context, {'nested': [1]})
        self.assertEqual(result.target_ids, ('N-1',))
        with self.assertRaises(FrozenInstanceError):
            result.run_id = 'other'

    def test_request_rejects_invalid_fields(self):
        for changes in [dict(inquiry_id=' '), dict(run_id=None), dict(operation=''),
                        dict(model=1), dict(session_id=''), dict(target_ids=['x', 'x']),
                        dict(target_ids=['']), dict(target_ids='x'),
                        dict(max_output_tokens=True), dict(max_output_tokens=0),
                        dict(max_output_tokens=1.5), dict(timeout=True),
                        dict(timeout=0), dict(timeout=float('inf'))]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_request(request(**changes))

    def test_timeout_must_fit_a_finite_runtime_float(self):
        self.assertEqual(validate_request(request(timeout=30)).timeout, 30)
        with self.assertRaises(ValueError):
            validate_request(request(timeout=10 ** 500))

    def test_json_validation_is_strict_and_errors_do_not_disclose_context(self):
        cycle = {}; cycle['secret'] = cycle
        for context in [[], {'secret': object()}, {'secret': float('nan')},
                        {1: 'secret'}, {'secret': (1,)}, {'secret': '\ud800'}, cycle]:
            with self.subTest(context_type=type(context)):
                with self.assertRaises(ValueError) as caught:
                    validate_request(request(context=context))
                self.assertNotIn('secret', str(caught.exception))

    def test_usage_states_and_detachment(self):
        self.assertEqual(unknown_usage()['input_tokens'], None)
        self.assertEqual(not_started_usage()['input_tokens'], 0)
        for source in [known(), known(est_cost=0.1, price_ref='price-v1'),
                       unknown_usage(), not_started_usage()]:
            self.assertEqual(validate_usage(source), source)
            self.assertIsNot(validate_usage(source), source)

    def test_usage_rejects_invalid_or_ambiguous_values(self):
        for value in [known(extra=1), {}, known(status='other'),
                      known(input_tokens=True), known(output_tokens=-1),
                      known(est_cost=-1), known(est_cost=float('inf')),
                      known(est_cost=True), known(est_cost=0),
                      known(price_ref=' '), dict(unknown_usage(), input_tokens=0),
                      dict(not_started_usage(), input_tokens=False)]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_usage(value)

    def test_valid_signals_are_detached(self):
        signals = [RunSignal('progress', text='working'), RunSignal('heartbeat'),
                   RunSignal('usage', usage=known()),
                   RunSignal('succeeded', proposal={'nodes': ['x']}, usage=unknown_usage()),
                   RunSignal('failed', reason='provider-error', usage=known()),
                   RunSignal('cancelled', reason='requested')]
        for signal in signals:
            self.assertEqual(validate_signal(signal), signal)
        source = signals[3]
        detached = validate_signal(source)
        source.proposal['nodes'].append('y')
        self.assertEqual(detached.proposal, {'nodes': ['x']})

    def test_signal_rejects_unsupported_combinations(self):
        signals = [RunSignal('other'), RunSignal('progress'),
                   RunSignal('progress', text='x', usage=known()),
                   RunSignal('heartbeat', text='x'), RunSignal('usage'),
                   RunSignal('usage', usage=unknown_usage()),
                   RunSignal('succeeded', proposal={}),
                   RunSignal('succeeded', proposal={'x': object()}),
                   RunSignal('failed'), RunSignal('cancelled', reason=' '),
                   RunSignal('failed', reason='x', proposal={'x': 1}),
                   RunSignal('heartbeat', provider_request_id=''),
                   RunSignal('succeeded', proposal={'x': 1}, usage=not_started_usage())]
        for signal in signals:
            with self.subTest(signal=signal), self.assertRaises(ValueError):
                validate_signal(signal)

    def test_fake_execution_is_lazy_and_closes(self):
        callbacks = []
        fake = FakeAdapter([RunSignal('heartbeat'), RuntimeError('failure')],
                           on_signal=lambda index, req: callbacks.append((index, req)))
        req = request()
        stream = fake.run(req)
        self.assertEqual(fake.calls, [])
        self.assertEqual(next(stream), RunSignal('heartbeat'))
        self.assertEqual(fake.calls, [req])
        with self.assertRaises(RuntimeError):
            next(stream)
        self.assertTrue(fake.closed)
        self.assertEqual(callbacks[0], (0, req))
        fake = FakeAdapter([RunSignal('heartbeat')])
        stream = fake.run(req)
        next(stream)
        stream.close()
        self.assertTrue(fake.closed)
