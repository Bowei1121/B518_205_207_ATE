# M6 local validation — conflicts and alarms

Date: 2026-10-09
Fixed review baseline: `31a9bccd5cb1534f2d17b99ad6ed3b4f461ffdd4`
Final program/test commit validated: `da94db305547307b8a0370c9da9569f07f671986`
Branch: `Multilingual/ticket-06`; GitHub branch was directly checked at the final program commit before this evidence document was added.

## Dependency and scope evidence

Git ancestry confirms that the M2 merge `f128d9f963f60d416d0eaf5917fa5eda87408280`, M4 merge `f7e24cd265fc173d5d113e7fb122083602f5e5fa`, M5 merge `cfb35480d890abeb8a03bc74360260dcd8d739e1`, and C3 commit `965d4224218fc96526e8e97141e3bb54b1ec70df` are ancestors of the M6 baseline. The implementation and prior validation records were also checked: M2 supplies the fixed bilingual event representation and audit/session contract; C1–C3 supply the compact/detail panes, draggable sash, field comparisons, path disambiguation, and candidate lifecycle. M5 native chooser validation is complete and is not an M6 dependency.

The current UI inventory covered the conflict window title and instructions, selectable conflict labels and locations, four comparison headings and values, detailed round/conflict/source/evidence labels, action/status text, and the round alarm title/body/status/acknowledge action. Human-facing strings use the shared catalog. Captured filenames, paths, SNs, source timestamps, source identities, result values, evidence, diagnostic text, and machine states remain raw. M6 adds no parsing, candidate ordering, decision, alarm acknowledgement, persistence, or release policy.

## Acceptance results

1. **Shared English/Traditional Chinese text; evidence stays raw — PASS.** The catalog contains both languages for conflict selection, comparison, detailed evidence, actions, and alarm states. Existing shared `term.test_round`, `term.source_time`, and `term.source_filename` terms are reused. `tests.test_language_catalog` checks catalog completeness, shared terminology and translated UI labels. True Tk tests inspect visible labels while preserving captured source evidence.
2. **In-place refresh preserves state — PASS.** The real-Tk conflict selection test switches the open window through the app language menu and verifies the selected conflict and reading position remain; alarm state remains pending until the operator acknowledges it. Refresh does not recreate the review item or invoke a decision.
3. **Multiple candidates, refresh/removal, and empty state — PASS.** Existing C3 tests exercise same-slot and cross-location candidates, refresh, removal, empty state, and hide/reopen. The M6 regression test clears the actual list selection without synthesizing a selection callback, lets the normal scheduled refresh run, and verifies stale comparison/detail text is cleared and decision controls disabled. C1/C2 tests continue to verify the paired snapshot, red/bold differing values, unknown values and same-name path hints.
4. **One bilingual record per operator action; existing policies remain — PASS.** The true-Tk action test performs one keep-original decision and one alarm acknowledgement. A fresh audit reader reconstructs one `conflict_resolved` and one `round_alarm_acknowledged` record, each carrying its existing identity, round, timestamp/sequence linkage and bilingual representation. The unresolved/unknown-source FAIL test remains in the full suite; no unknown-source adoption path is introduced.
5. **Controlled source → shared round → Tk → disk; KVM and other-position collection — PASS.** Real Atlas source data creates a conflict through the shared round path. The open dialog is switched, the fixed KVM marker geometry remains viewable, and another source position completes while review remains open. A fresh audit reader reconstructs the operator actions and remaining round state. The existing round alarm test verifies that language refresh itself does not acknowledge the alarm.

## Commands and results

From `B518 Log Solution/`:

```text
B518_TK_TESTS=1 PYTHONPATH=src python3 -m unittest tests.test_language_catalog tests.test_log_solution_ui.LogSolutionUiTests.test_conflict_review_disables_resolution_when_selection_is_cleared tests.test_log_solution_ui.LogSolutionUiTests.test_conflict_review_tracks_same_slot_candidates_through_refresh_resolution_and_reopen tests.test_log_solution_ui.LogSolutionUiTests.test_sample_platform_conflicts_stay_consistent_through_real_tk_and_disk_rebuild tests.test_log_solution_ui.LogSolutionUiTests.test_atlas_round_shows_nonblocking_conflict_and_releases_after_other_slot_finishes tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_conflict_selection_keeps_both_sections_on_same_snapshot tests.test_log_solution_ui.LogSolutionUiTests.test_atlas_conflict_with_same_filename_from_new_archive_path_shows_real_tk_hint tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_close_keeps_conflict_and_alarm_actions_available -v
```

Result: 13 tests passed (11.538 seconds), including real Tk interactions and disk reconstruction.

```text
B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py
```

Result on final program/test commit `da94db3`: 335 tests passed, 83.317 seconds, `OK`. This full suite ran with access to the desktop Tk session. It includes the C1/C2/C3 and round/audit/KVM regressions; it is not a claim that M7–M10 or all parent-spec scenarios are delivered.

```text
python3 -m compileall -q src tests
git diff --check
```

Both commands passed. Repository search found no configured mypy, Pyright, or other project type-check command; type checking is therefore not claimed.

## Review and boundaries

Standards and Spec reviews were run in parallel against the fixed baseline above and final program/test commit `da94db3`. Both reported zero actionable findings. Earlier review findings were corrected before this final pass: duplicate conflict-label setup was consolidated; shared terminology was reused; and a cleared selection now clears stale detail/comparison content and disables decisions during ordinary refresh. The full suite was rerun after these program changes.

M6 delivers conflict/alarm window translations and in-place state-preserving refresh. It retains C1–C3 layouts and policies. M7 save/close language policy, M8 historical-message recognition, M9 App-event retention, and M10 full bundle/release verification remain outside this ticket. The parent spec's remaining full-app and deployment cases are not marked complete here.

## GitHub merge and post-merge verification

Before merge, the target worktree was clean, local `B518-Log-Solution` was exactly the direct GitHub head `31a9bccd5cb1534f2d17b99ad6ed3b4f461ffdd4`, and the ticket branch was `41bf0fc5ad5d19044cb6e4aae1b59490a156d786`. The ticket branch contained the target; no remote commits needed integration.

GitHub merge commit: `daba4822566f944e603d065b5319674f83c99311`.

On merged `B518-Log-Solution`, `B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py` passed all 335 tests in 85.007 seconds. `python3 -m compileall -q src tests` and `git diff --check` also passed. The merged test run used the desktop Tk session.

The merge and post-merge test passed. GitHub main and final documentation push SHA checks will be recorded after publication. No remote issue was modified. Company Gitea synchronization remains deferred to Monday by user instruction. Keep the local and GitHub M6 ticket branches until Gitea is directly confirmed, then complete the authorized cleanup.
