import copy
import unittest

from inquiry.events import EventValidationError, validate_event


def event(seq=1, changes=None, **overrides):
    value = {
        'schema_version': 1, 'event_id': f'event-{seq}', 'seq': seq,
        'inquiry_id': 'I-001', 'actor': 'human:local', 'at': '2026-09-17T00:00:00Z',
        'type': 'changes-committed',
        'changes': changes if changes is not None else [
            {'kind': 'InquiryCreated', 'seed': '반복 실수를 줄이고 싶다',
             'frame': {'question': '다음 세션에 지침을 어떻게 전달할까?'}}],
    }
    value.update(overrides)
    return value


class EventTests(unittest.TestCase):
    def test_validates_and_detaches_nested_data(self):
        source = event()
        result = validate_event(source)
        self.assertEqual(result, source)
        source['changes'][0]['frame']['question'] = 'changed'
        self.assertNotEqual(result, source)

    def test_envelope_fields_are_strict(self):
        invalid = [event(seq=True), event(seq=0), event(schema_version=2),
                   event(schema_version=True), event(type='unknown'), event(event_id=' '),
                   event(actor=None), event(inquiry_id=''), event(changes=[]),
                   event(at='2026-09-17'), event(at='2026-09-17T09:00:00+09:00'),
                   event(at='2026-02-30T00:00:00Z'), event(extra='silently ignored')]
        for source in invalid:
            with self.subTest(source=source), self.assertRaises(EventValidationError):
                validate_event(source)

    def test_bad_batch_is_rejected_whole(self):
        source = event()
        source['changes'].append({'kind': 'NotSupported'})
        before = copy.deepcopy(source)
        with self.assertRaises(EventValidationError):
            validate_event(source)
        self.assertEqual(source, before)

    def test_change_fields_and_json_are_strict(self):
        invalid = [
            {'kind': 'FramingStarted', 'session_id': 'S-1'},
            {'kind': 'FramingStarted', 'session_id': '', 'seed': 'seed'},
            {'kind': 'InquiryCreated', 'seed': 'seed', 'frame': []},
            {'kind': 'InquiryCreated', 'seed': 'seed', 'frame': {}, 'typo': 1},
            {'kind': 'InquiryCreated', 'seed': 'seed', 'frame': {'score': float('nan')}},
            {'kind': 'InquiryCreated', 'seed': 'seed', 'frame': {1: 'bad key'}},
            {'kind': 'InquiryCreated', 'seed': 'seed', 'frame': {'values': (1, 2)}},
            {'kind': 'InquiryCreated', 'seed': 'seed', 'frame': {'text': '\ud800'}},
        ]
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(EventValidationError):
                validate_event(event(changes=[change]))


if __name__ == '__main__':
    unittest.main()
