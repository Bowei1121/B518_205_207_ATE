import unittest

from b518_log_solution import B518LogSolutionApp
from language_catalog import ENGLISH, TRADITIONAL_CHINESE


class RecoveryActionHintTests(unittest.TestCase):
    def make_app(self, language, selected=None):
        app = B518LogSolutionApp.__new__(B518LogSolutionApp)
        app.current_language = language
        app._closing_ui = False
        app._recovery_selected_action = selected
        return app

    def test_unselected_actions_explain_the_required_item_type_in_each_language(self):
        expectations = (
            (ENGLISH, "Select a startup failure to enable this action.",
             "Select a round awaiting cancellation to enable this action."),
            (TRADITIONAL_CHINESE, "請選取啟動異常，才能使用此操作。",
             "請選取待取消輪次，才能使用此操作。"),
        )
        for language, reset_reason, cancel_reason in expectations:
            with self.subTest(language=language):
                app = self.make_app(language)
                self.assertIn(reset_reason, app._recovery_hint_text("reset_start_failure"))
                self.assertIn(cancel_reason, app._recovery_hint_text("cancel_unverified_round"))

    def test_selecting_the_other_action_type_keeps_the_hint_specific(self):
        app = self.make_app(ENGLISH, ("cancel_round", "round-1"))
        self.assertIn("Select a startup failure", app._recovery_hint_text("reset_start_failure"))

        app._recovery_selected_action = ("start_failure", "request-1")
        self.assertIn("Select a round awaiting cancellation",
                      app._recovery_hint_text("cancel_unverified_round"))

    def test_action_hints_explain_results_without_collapsing_distinct_operations(self):
        expectations = (
            (ENGLISH,
             "allow a new manual start", "does not retry monitoring or start the ATE",
             "withdraws delivery", "keeps its results and handling record",
             "does not delete records or mark products as failed"),
            (TRADITIONAL_CHINESE,
             "由人員手動重新開始", "不會重試監控或啟動 ATE",
             "撤回本輪結果交付", "保留結果與處置紀錄",
             "不會刪除紀錄或把產品判為失敗"),
        )
        for language, reset_effect, no_retry, cancel_effect, retained, not_fail in expectations:
            with self.subTest(language=language):
                app = self.make_app(language, ("start_failure", "request-1"))
                reset_hint = app._recovery_hint_text("reset_start_failure")
                self.assertIn(reset_effect, reset_hint)
                self.assertIn(no_retry, reset_hint)

                app._recovery_selected_action = ("cancel_round", "round-1")
                cancel_hint = app._recovery_hint_text("cancel_unverified_round")
                self.assertIn(cancel_effect, cancel_hint)
                self.assertIn(retained, cancel_hint)
                self.assertIn(not_fail, cancel_hint)


if __name__ == "__main__":
    unittest.main()
