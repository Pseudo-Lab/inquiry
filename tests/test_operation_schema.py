import copy
import unittest

from inquiry.model import Hypothesis
from inquiry.operation_schema import OPERATION_SCHEMAS, eligible_targets, validate_operation
from tests.operation_fixtures import deepen_output, synthesis_output


class OperationSchemaTests(unittest.TestCase):
    def test_deepen_output_is_strict_detached_json(self):
        source = deepen_output()
        self.assertEqual(set(OPERATION_SCHEMAS), {'deepen', 'challenge', 'synthesize'})
        result = validate_operation('deepen', source)
        self.assertEqual(result, source)
        source['reason'] = None
        self.assertNotEqual(result, source)

    def test_rejects_unknown_fields_bad_json_blank_text_bounds_and_duplicates(self):
        invalid = []
        value = deepen_output(); value['extra'] = True; invalid.append(('deepen', value))
        value = deepen_output(); value['reason'] = ' '; invalid.append(('deepen', value))
        value = deepen_output(); value['assumptions'] = []; value['falsified_if'] = []; invalid.append(('deepen', value))
        value = deepen_output(); value['assumptions'] = ['x'] * 9; invalid.append(('deepen', value))
        value = deepen_output(); value['assumptions'] = [' Same  text ', 'same TEXT']; invalid.append(('deepen', value))
        value = deepen_output(); value['assumptions'] = ('not', 'a list'); invalid.append(('deepen', value))
        value = deepen_output(); value['bad'] = float('nan'); invalid.append(('deepen', value))
        for operation, payload in invalid:
            with self.subTest(operation=operation, payload=repr(payload)), self.assertRaises(ValueError):
                validate_operation(operation, payload)
        for operation in ('unknown', 'synthesize'):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                validate_operation(operation, {})

    def test_target_eligibility_is_sorted_unique_and_operation_specific(self):
        active = {status: Hypothesis('H-' + status, 't', 'c', (), status=status)
                  for status in ('suggested', 'exploring', 'supported', 'contested')}
        inactive = Hypothesis('H-closed', 't', 'c', (), status='human-closed')
        hypotheses = {node.id: node for node in (*active.values(), inactive)}
        self.assertEqual(eligible_targets('deepen', hypotheses, ['H-supported']), ('H-supported',))
        self.assertEqual(eligible_targets('challenge', hypotheses, ['H-supported']), ('H-supported',))
        self.assertEqual(eligible_targets('synthesize', hypotheses,
                                         ['H-contested', 'H-supported']),
                         ('H-contested', 'H-supported'))
        for targets in (['H-closed'], ['missing'], ['H-supported', 'H-supported'],
                        ['H-supported', 'H-contested']):
            with self.subTest(targets=targets), self.assertRaises(ValueError):
                eligible_targets('deepen', hypotheses, targets)
        with self.assertRaises(ValueError):
            eligible_targets('synthesize', hypotheses, ['H-supported'])

    def test_synthesis_output_is_strict_and_preserves_unresolved_differences(self):
        source = synthesis_output()
        self.assertEqual(validate_operation('synthesize', source), source)
        source['unresolved'] = ['same', ' SAME ']
        with self.assertRaises(ValueError):
            validate_operation('synthesize', source)


if __name__ == '__main__':
    unittest.main()
