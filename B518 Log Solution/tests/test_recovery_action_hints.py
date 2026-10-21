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


if __name__ == "__main__":
    unittest.main()
