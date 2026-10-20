import unittest
from pathlib import Path
from unittest.mock import Mock

from monitoring_round import RoundState
from round_start_flow import RoundStartFlow, StartFailurePhase, StartFlowStatus


class Snapshot:
    def __init__(self, state=RoundState.READY, cancellation_available=False):
        self.state = state
        self.cancellation_available = cancellation_available


class RoundStartFlowTests(unittest.TestCase):
    def setUp(self):
        self.coordinator = Mock()
        self.coordinator.start_failure_snapshot.return_value = None
        self.coordinator.snapshot.return_value = None
        self.profile = object()
        self.snapshot = Snapshot(RoundState.PREPARING)
        self.prepared = Mock()
        self.prepared.start.return_value = self.snapshot
        self.preparation = Mock()
        self.preparation.prepare.return_value = self.prepared
        self.flow = RoundStartFlow(self.preparation)
        self.select_profile = Mock(return_value=self.profile)
        self.save_preferences = Mock()

    def run_flow(self, closing=False):
        return self.flow.run(
            self.coordinator, self.select_profile, Path("sessions"),
            self.save_preferences, closing=closing,
        )

    def test_valid_start_saves_before_accepting_the_prepared_round(self):
        result = self.run_flow()

        self.assertEqual(result.status, StartFlowStatus.ACCEPTED)
        self.assertIs(result.snapshot, self.snapshot)
        self.select_profile.assert_called_once_with()
        self.preparation.prepare.assert_called_once_with(
            self.profile, Path("sessions"), async_session_writes=True,
        )
        self.save_preferences.assert_called_once_with()
        self.prepared.start.assert_called_once_with(self.coordinator, run_async=True)

    def test_profile_validation_failure_does_not_save_or_start(self):
        self.preparation.prepare.side_effect = ValueError("invalid profile")

        result = self.run_flow()

        self.assertEqual(result.status, StartFlowStatus.FAILED)
        self.assertEqual(result.failure.phase, StartFailurePhase.PROFILE_VALIDATION)
        self.assertEqual(result.failure.diagnostic, "invalid profile")
        self.save_preferences.assert_not_called()
        self.prepared.start.assert_not_called()

    def test_preference_failure_does_not_accept_a_round(self):
        self.save_preferences.side_effect = OSError("disk full")

        result = self.run_flow()

        self.assertEqual(result.status, StartFlowStatus.FAILED)
        self.assertEqual(result.failure.phase, StartFailurePhase.PREFERENCE_SAVE)
        self.assertEqual(result.failure.diagnostic, "disk full")
        self.prepared.start.assert_not_called()

    def test_source_start_failure_keeps_the_coordinator_snapshot(self):
        self.prepared.start.side_effect = RuntimeError("source denied")
        self.coordinator.snapshot.side_effect = [None, self.snapshot]

        result = self.run_flow()

        self.assertEqual(result.status, StartFlowStatus.FAILED)
        self.assertEqual(result.failure.phase, StartFailurePhase.SOURCE_START)
        self.assertEqual(result.failure.diagnostic, "source denied")
        self.assertIs(result.failure.snapshot, self.snapshot)

    def test_busy_states_failure_cancellation_and_closing_share_the_same_gate(self):
        for state in (RoundState.PREPARING, RoundState.RUNNING, RoundState.AWAITING_REVIEW):
            with self.subTest(state=state):
                self.coordinator.snapshot.return_value = Snapshot(state)
                result = self.run_flow()
                self.assertEqual(result.status, StartFlowStatus.REJECTED)
                self.select_profile.assert_not_called()

        self.coordinator.snapshot.return_value = Snapshot(cancellation_available=True)
        self.assertEqual(self.run_flow().status, StartFlowStatus.REJECTED)

        self.coordinator.snapshot.return_value = None
        self.coordinator.start_failure_snapshot.return_value = object()
        self.assertEqual(self.run_flow().status, StartFlowStatus.REJECTED)

        self.coordinator.start_failure_snapshot.return_value = None
        self.assertEqual(self.run_flow(closing=True).status, StartFlowStatus.REJECTED)
        self.select_profile.assert_not_called()

    def test_nested_request_during_preparation_is_rejected(self):
        nested_results = []

        def prepare(*_args, **_kwargs):
            nested_results.append(self.run_flow())
            return self.prepared

        self.preparation.prepare.side_effect = prepare
        result = self.run_flow()

        self.assertEqual(result.status, StartFlowStatus.ACCEPTED)
        self.assertEqual(nested_results[0].status, StartFlowStatus.REJECTED)
        self.assertEqual(self.prepared.start.call_count, 1)


if __name__ == "__main__":
    unittest.main()
