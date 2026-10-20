"""Desktop input permission is a prerequisite, not a reason to skip acceptance."""
import unittest
from unittest.mock import Mock

from check_macos_native_test_access import require_native_event_access


class NativeEventAccessTests(unittest.TestCase):
    def test_denied_event_posting_stops_acceptance_with_actionable_diagnostic(self):
        preflight = Mock(return_value=False)
        with self.assertRaisesRegex(RuntimeError, "Accessibility.*No test was skipped"):
            require_native_event_access(preflight)
        preflight.assert_called_once_with()

    def test_existing_event_posting_permission_allows_acceptance(self):
        preflight = Mock(return_value=True)
        require_native_event_access(preflight)
        preflight.assert_called_once_with()
