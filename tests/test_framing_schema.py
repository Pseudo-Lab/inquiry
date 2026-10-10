"""Protocol validation and handcrafted fixtures, not live model quality tests."""

import copy
import importlib
import json
from pathlib import Path
import unittest


def control(**changes):
    value = dict(mode='explore', mode_rationale='탐색', done=False,
                 question_rationale='맥락 확인', questions=['목적?', '사용처?', '범위?'])
    value.update(changes)
    return value


def frame():
    return dict(central_question='무엇을 검증할까?', purpose='방향 선택',
                use_context='기획', current_belief='미정', criteria=['미정'],
                scope=dict(include=['사용 경험'], exclude=[]), open_questions=[],
                hypotheses=[dict(candidate_id='H-1', title='빈도', claim='빈도가 중요하다',
                                 difference='빈도를 기준으로 본다'),
                            dict(candidate_id='H-2', title='깊이', claim='깊이가 중요하다',
                                 difference='깊이를 기준으로 본다')])


class FramingSchemaTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('inquiry.framing_schema'),
                             'pure framing validators must exist')
        self.schema = importlib.import_module('inquiry.framing_schema')

    def test_question_counts_and_completion_boundaries(self):
        for asked in range(6):
            for done in (False, True):
                for count in range(7):
                    value = control(done=done, questions=[f'질문 {i}' for i in range(count)],
                                    question_rationale='' if done else '추가 맥락')
                    valid = ((done and asked >= 3 and count == 0) or
                             (not done and ((asked == 0 and count == 3) or
                              (0 < asked < 5 and 1 <= count <= min(2, 5 - asked)))))
                    with self.subTest(asked=asked, done=done, count=count):
                        if valid:
                            self.assertEqual(self.schema.validate_questions(value, asked), value)
                        else:
                            with self.assertRaises(ValueError):
                                self.schema.validate_questions(value, asked)

    def test_controls_reject_wrong_types_fields_and_duplicates(self):
        for asked in (True, False, -1, 6, 1.0, '0', None):
            with self.subTest(asked=asked), self.assertRaises(ValueError):
                self.schema.validate_questions(control(), asked)
        for changes in [dict(mode='other'), dict(mode=[]), dict(mode_rationale=' '),
                        dict(done=1), dict(question_rationale=''), dict(extra='secret'),
                        dict(questions=['x', 'x', 'y']), dict(questions=['x', ' ', 'y']),
                        dict(questions=('x', 'y', 'z')), dict(questions=['x', 1, 'z'])]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.schema.validate_questions(control(**changes), 0)
        for rationale in (' ', 'unexpected'):
            with self.assertRaises(ValueError):
                self.schema.validate_questions(control(done=True, questions=[],
                                                      question_rationale=rationale), 3)
        value = control(); del value['mode']
        with self.assertRaises(ValueError):
            self.schema.validate_questions(value, 0)

    def test_valid_outputs_are_deeply_detached(self):
        value = frame()
        result = self.schema.validate_frame(value)
        value['hypotheses'][0]['claim'] = '수정'
        value['scope']['include'].append('추가')
        self.assertEqual(result, frame())
        value = control()
        result = self.schema.validate_questions(value, 0)
        value['questions'].append('추가')
        self.assertEqual(result, control())

    def test_frame_rejects_malformed_shapes_and_normalized_duplicates(self):
        invalid = []
        for key in frame():
            value = frame(); del value[key]; invalid.append(value)
        for key in ('central_question', 'purpose', 'use_context', 'current_belief'):
            value = frame(); value[key] = ' '; invalid.append(value)
        for changes in [dict(confidence=0.8), dict(criteria=[]), dict(criteria=[' ']),
                        dict(open_questions=['']), dict(scope=dict(include=[], exclude=[])),
                        dict(scope=dict(include=['x'], exclude=[], extra='x')),
                        dict(scope=dict(include=['x'], exclude=[1])),
                        dict(hypotheses=[]), dict(hypotheses=frame()['hypotheses'][:1])]:
            invalid.append(dict(frame(), **changes))
        for key in ('candidate_id', 'title', 'claim', 'difference'):
            value = frame(); value['hypotheses'][0][key] = ''; invalid.append(value)
        value = frame(); value['hypotheses'][0]['confidence'] = 1; invalid.append(value)
        for key in ('candidate_id', 'title', 'claim'):
            value = frame()
            value['hypotheses'][0][key] = 'Same  Text'
            value['hypotheses'][1][key] = 'Same  Text' if key == 'candidate_id' else ' same\n text '
            invalid.append(value)
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.schema.validate_frame(value)
        for count in (2, 3, 4, 5):
            value = frame()
            value['hypotheses'] = [dict(candidate_id=str(i), title=f'제목 {i}',
                                        claim=f'주장 {i}', difference='구분') for i in range(count)]
            if count <= 4:
                self.schema.validate_frame(value)
            else:
                with self.assertRaises(ValueError):
                    self.schema.validate_frame(value)

    def test_invalid_json_errors_do_not_echo_content(self):
        cycle = {}; cycle['secret'] = cycle
        for bad in (object(), float('nan'), float('inf'), '\ud800', cycle, (1,), {1: 'secret'}):
            for validator, value in ((self.schema.validate_frame, frame()),
                                     (lambda payload: self.schema.validate_questions(payload, 0), control())):
                value['secret'] = bad
                with self.assertRaises(ValueError) as caught:
                    validator(value)
                self.assertNotIn('secret', str(caught.exception))

    def test_exported_schemas_are_strict_json_objects(self):
        for schema, expected in ((self.schema.CONTROL_SCHEMA, control()),
                                 (self.schema.FRAME_SCHEMA, frame())):
            self.assertEqual(json.loads(json.dumps(schema, allow_nan=False)), schema)
            self.assertEqual(set(schema['required']), set(expected))
            self.assertEqual(set(schema['properties']), set(expected))
            self.assertFalse(schema['additionalProperties'])
        scope = self.schema.FRAME_SCHEMA['properties']['scope']
        hypothesis = self.schema.FRAME_SCHEMA['properties']['hypotheses']['items']
        for schema in (scope, hypothesis):
            self.assertFalse(schema['additionalProperties'])
            self.assertEqual(set(schema['required']), set(schema['properties']))

    def test_five_handcrafted_fixtures_match_prototype_seeds(self):
        root = Path(__file__).resolve().parents[1]
        fixtures = json.loads((root / 'tests/fixtures/framing.json').read_text())
        self.assertEqual({item['sample'] for item in fixtures},
                         {'research', 'product', 'policy', 'creative', 'thought-experiment'})
        self.assertEqual(len(fixtures), 5)
        for item in fixtures:
            self.assertEqual(set(item), {'sample', 'seed', 'frame'})
            seed = root / 'prototypes/m1a-framing/samples' / (item['sample'] + '.txt')
            self.assertEqual(item['seed'], seed.read_text().strip())
            self.schema.validate_frame(copy.deepcopy(item['frame']))
