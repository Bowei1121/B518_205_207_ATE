import unittest
from types import SimpleNamespace

from b518_log_solution import B518LogSolutionApp


class NotificationItemCountTests(unittest.TestCase):
    def make_app(self, failure=None, snapshots=None, statuses=(), unsaved=()):
        snapshots = snapshots or {}
        app = B518LogSolutionApp.__new__(B518LogSolutionApp)
        app.rounds = SimpleNamespace(
            start_failure_snapshot=lambda: failure,
            archive_statuses=lambda: tuple(statuses),
            round_snapshot=lambda round_id: snapshots.get(round_id),
            unsaved_rounds=lambda: tuple(unsaved),
        )
        return app

    @staticmethod
    def snapshot(round_id, *, alarm=None, save_state="complete", retry=False,
                 save_errors=(), cancellation=False):
        return SimpleNamespace(
            round_id=round_id, round_alarm=alarm, save_state=save_state,
            retry_in_progress=retry, save_errors=save_errors,
            cancellation_available=cancellation,
        )

    @staticmethod
    def status(round_id, *, state="complete", save_state="complete",
               cleanup_eligible=False, protected=False):
        return SimpleNamespace(
            round_id=round_id, status="protected" if protected else state,
            save_state=save_state, cleanup_eligible=cleanup_eligible,
        )

    def test_zero_items_remain_zero(self):
        app = self.make_app()
        self.assertEqual(app._pending_notification_count(), 0)

    def test_start_failure_and_waiting_cancellation_are_counted(self):
        failure = SimpleNamespace(request_id="request-1")
        pending_cancel = self.snapshot("round-1", cancellation=True)
        app = self.make_app(
            failure=failure, snapshots={"round-1": pending_cancel},
            statuses=[self.status("round-1")],
        )
        self.assertEqual(app._pending_notification_count(), 2)

    def test_same_alarm_and_save_failure_are_counted_once_across_sources(self):
        alarm = SimpleNamespace(round_id="round-1", alarm_id="alarm-1",
                                acknowledged_at=None)
        failed = self.snapshot("round-1", alarm=alarm, save_state="failed")
        app = self.make_app(
            snapshots={"round-1": failed},
            statuses=[self.status("round-1", state="failed", save_state="failed")],
            unsaved=[failed],
        )
        self.assertEqual(app._pending_notification_count(), 3)

    def test_independent_round_failures_and_alarms_are_not_coalesced(self):
        first = self.snapshot("round-1", alarm=SimpleNamespace(
            round_id="round-1", alarm_id="alarm-1", acknowledged_at=None))
        second = self.snapshot("round-2", save_state="failed")
        app = self.make_app(
            snapshots={"round-1": first, "round-2": second},
            statuses=[
                self.status("round-1"),
                self.status("round-2", state="failed", save_state="failed"),
            ],
        )
        self.assertEqual(app._pending_notification_count(), 3)


if __name__ == "__main__":
    unittest.main()
