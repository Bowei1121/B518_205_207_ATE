# LI8 local integration evidence

Candidate: `codex/li8-local-integration-acceptance`
Comparison base: `b933600e0c5f835209502de0e3e210395acb5fb3`
Acceptance checklist: [LI8_LOCAL_ACCEPTANCE.md](../../../../../docs/refactoring/log-instrument-tickets/LI8_LOCAL_ACCEPTANCE.md)
Story coverage: [LI8_STORY_EVIDENCE_MATRIX.md](../../../../../docs/refactoring/log-instrument-tickets/LI8_STORY_EVIDENCE_MATRIX.md)

## Runtime and capture method

Real Tk runs used macOS 15.8.1 x86_64, Python 3.11.7, Tk 8.6.12 in an authorized Aqua desktop session. No physical KVM was connected. The LI1, LI2, LI4 and LI5 smoke programs run the actual B518 Tk app and query its public round state, controls, results and fresh disk reader.

The original Quartz window captures from LI1, LI2 and LI4 produced all-black PNGs in this desktop session. They are retained with the suffix `-quartz-black-invalid.png` for audit and are not acceptance evidence. The smoke capture now uses `NSWindow.contentView()`'s `bitmapImageRepForCachingDisplayInRect_` and `cacheDisplayInRect_toBitmapImageRep_` on the mapped Tk App window. This is a live Tk view cache, not a WindowServer screenshot or synthetic redraw. The new images were visually checked and are readable. LI5 also has readable actual-app evidence. LI7 geometry screenshots use the same view-cache method, with separate Quartz on-screen bounds and Tk widget measurements in JSON.

## Commands and results

All commands below ran from `B518 Log Solution/` with `PYTHONPATH=src` unless shown otherwise.

- Contract tests: `PYTHONPATH=src /opt/anaconda3/bin/python3 -m unittest tests.test_kvm_display_contract -v` — 11 passed.
- Core lifecycle, persistence, event store and contract regression: `PYTHONPATH=src /opt/anaconda3/bin/python3 -m unittest tests.test_monitoring_round tests.test_audit_records tests.test_app_event_store tests.test_kvm_display_contract -q` — 127 passed in 12.208s.
- Integrated real Tk UI: `B518_TK_TESTS=1 PYTHONPATH=src /opt/anaconda3/bin/python3 -X faulthandler -m unittest tests.test_m10_integration -v` — 7 passed in 14.400s in authorized Aqua session. The sandbox-only attempt aborted during native Tk/AppKit root initialization (hiservices XPC / `NSMenuItem`), before assertions.
- Disk/UI regression: `B518_TK_TESTS=1 B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/li8-integration/disk-ui-regression PYTHONPATH=src /opt/anaconda3/bin/python3 -X faulthandler -m unittest tests.test_log_solution_ui.LogSolutionUiTests.test_queued_prior_round_event_cannot_change_the_new_round_ui tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_retry_button_recovers_disk_record_once_without_blocking_ui tests.test_log_solution_ui.LogSolutionUiTests.test_close_failure_keeps_window_open_and_real_retry_rebuilds_complete_audit tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_historical_reader_selects_and_localizes_disk_records_without_rewriting -v` — 4 passed in 23.874s.
- LI1 lifecycle real app: `PYTHONPATH=src B518_LI1_EVIDENCE_DIR=docs/refactoring/evidence/li8-integration/li1-lifecycle /opt/anaconda3/bin/python3 tools/smoke_li1_preparation_app.py` — passed; READY/PREPARING, MONITORING, TESTING activity and PASS results captured.
- LI2 stop/rebuild real app: `PYTHONPATH=src B518_LI2_EVIDENCE_DIR=docs/refactoring/evidence/li8-integration/li2-manual-stop /opt/anaconda3/bin/python3 tools/smoke_li2_manual_stop_app.py` — passed; prep-stop REVIEW and explicit cancellation, ready mixed terminal manual-stop completion, conflicts, and fresh disk reconstruction.
- LI4 deadline/alarm real app: `PYTHONPATH=src B518_LI4_EVIDENCE_DIR=docs/refactoring/evidence/li8-integration/li4-start-alarm /opt/anaconda3/bin/python3 tools/smoke_li4_start_alarm_app.py` — passed; deadline review and alarm acknowledgement to available completion result.
- LI5 cancellation/new-round real app: `PYTHONPATH=src B518_LI5_EVIDENCE_DIR=docs/refactoring/evidence/li8-integration/li5-manual-cancel /opt/anaconda3/bin/python3 tools/smoke_li5_manual_cancel_app.py` — passed; manual stop and prep timeout review/acknowledgement/cancellation, new round, prior-round handoff isolation.
- LI7 Tk geometry matrix: `B518_TK_TESTS=1 B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/li8-integration/li7-geometry-language-matrix PYTHONPATH=src /opt/anaconda3/bin/python3 -X faulthandler -m unittest tests.test_log_solution_ui.LogSolutionUiTests.test_li7_geometry_at_both_scalings_and_all_capacities` — 1 test passed in 4.682s. It generated 16 JSON and 16 readable view-cache PNG captures: scaling 1.0/1.5 × capacity 1/10/11/20 × English/Traditional Chinese. Capacity changes used visible Settings Profile Editor entries and Apply, followed by language menu switching.

## LI6 foreground revalidation

The isolated candidate run and isolated baseline run both used this command, with separate evidence directories and one Tk process per command:

`B518_TK_TESTS=1 B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/li8-integration/li6-foreground-isolated-candidate PYTHONPATH=src /opt/anaconda3/bin/python3 scripts/run_tests.py test_li6_foreground`

`B518_TK_TESTS=1 B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/li8-integration/li6-foreground-isolated-baseline PYTHONPATH=src /opt/anaconda3/bin/python3 scripts/run_tests.py test_li6_foreground`

Both ran one test and reached only the final minimize/restore focus assertion before failing after about 16 seconds. Both reported `minimize-restore focus changed to .; key window=None`. Earlier checks in that test passed for activity/result events, normal completion, timeout, manual stop, preserving focus in another Entry, and not forcing topmost. This is a partial revalidation, not a pass for LI8 AC6. The prior completed LI6 run remains linked in the story matrix; no production focus code or assertion was changed here.

## Evidence folders

- `li1-lifecycle/` — four lifecycle screens, original Quartz black PNGs retained as invalid, run metadata.
- `li2-manual-stop/` — five review/cancel/manual-stop screens, disk reconstruction, original Quartz black PNGs retained as invalid.
- `li4-start-alarm/` — review/alarm/complete screens, original Quartz black PNGs retained as invalid.
- `li5-manual-cancel/` — review, alarm acknowledgement, cancellation and new-round screens.
- `li6-foreground/` and `li6-foreground-rerun/` — earlier candidate evidence; `li6-foreground-isolated-candidate/` and `li6-foreground-isolated-baseline/` — isolated comparison evidence.
- `li7-geometry-language-matrix/` — 16-case scaling/capacity/language matrix and combined JSON.
- `disk-ui-regression/` — save failure/retry, close protection and historical reader UI captures.

## Scope and limits

This verifies Log Solution local public round behavior, persisted records, the real Tk app and local display contract. It does not test KVM_Log recognition, JetKVM, Dock automation, LabVIEW or field ATE flow, and adds no TCP or ACK bridge. Current LI8 revalidation remains incomplete because AC6 minimize/restore focus did not pass in either candidate or base on this Aqua session.
