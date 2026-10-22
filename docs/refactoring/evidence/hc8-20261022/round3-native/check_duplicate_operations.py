import sys
import unittest
from pathlib import Path
from unittest.mock import patch

root = Path('/private/tmp/B518-HC8-acceptance/B518 Log Solution')
for directory in ('src', 'tools', 'scripts', 'tests'):
    sys.path.insert(0, str(root / directory))

import test_m10_integration as integration

read_audit = integration.read_round_audit
operation_kinds = {'conflict_resolved', 'round_alarm_acknowledged', 'round_cancelled'}

def duplicate_operations(path):
    audit = read_audit(path)
    duplicates = [event for event in audit['events'] if event['kind'] in operation_kinds]
    return {**audit, 'events': [*audit['events'], *duplicates]}

case = integration.M10SourceIntegrationTests(
    'test_real_source_all_windows_switch_cancel_and_single_decisions')
with patch.object(integration, 'read_round_audit', side_effect=duplicate_operations):
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([case]))

detected = (len(result.failures) == 1 and not result.errors and
            'Counter' in result.failures[0][1] and "': 2" in result.failures[0][1])
print('DUPLICATE_OPERATION_MUTATION_DETECTED=' + str(detected))
sys.exit(0 if detected else 1)
