# C3 local validation — App-event cleanup reasons

Date: 2026-10-13 (Asia/Taipei)
Ticket: cleanup-reason C3, GitHub #35 (parent #28)
Branch: `LanguageRefresh/ticket-07`
Fixed review base: `f80e86a51907988613185155ed69552c9f392426`
Code commits: `4e19cd608d20362feaeb96912c8a277e955d11af`, `cdaa1ddf6a9f12d25ef5fd90c901ef97c5a8c534`, `373da606bc60516db3a91c678485a3f8417c7ec4`, `e1b4e3ac0f84c1c9a8d146d579c3170b82dc893a`, `cd1fc76aae1892947c63bc948d6cbc666b6c0667`, `34c38112232033e52985b616584a56a20b2eac08`, `14c83faae1b556a8f1bd051e339046e82d6f2f4d`, `fffe809`, `4cb353f` (latest code/test commit; final full-Tk gate remains blocked)

## Baseline, dependencies, and scope

The repository root is the B518 repository and the Python project is `B518 Log Solution/`. The isolated C3 worktree is `/private/tmp/B518-LanguageRefresh-C3`. Its fixed review base is the `B518-Log-Solution` tip before C3 changes. The base contains C1 and C2 in its ancestry. C1's final validation records the fixed-base reviews, fresh-reader and true-Tk evidence, the reproduced-and-resolved notice reopen/Escape lifecycle case, and its post-integration full-suite pass. C2's final validation records its round/archive producer migration and full-suite/review results. C3 relies directly on C1; it does not import or redo C2. The App-event reason remains compatible with the existing round summary contract. C4 still owns complete screen migration and parent second-item acceptance.

At the start, direct `git ls-remote` queries found both Gitea and GitHub `B518-Log-Solution` at `f80e86a51907988613185155ed69552c9f392426`; the ticket ref did not yet exist. No pre-existing mainline edits or artifacts were brought into the C3 worktree. The original mainline worktree's local summary edits were left untouched.

## Producer and persistence inventory

| Concern | Existing path and C3 behavior |
| --- | --- |
| App journal | `AppEventStore` retains the existing versioned journal, event identifiers, original event timestamps, serials, pending-save state, protected/retired serial ranges, managed root pinning, atomic replacement, and parent-directory durability checks. C3 does not create a second journal or alter its format. |
| Cleanup producer | `AppEventStore.cleanup_expired()` captures C1 reason records at cleanup decision/error sites: empty/missing journal, deleted events, not-yet-expired events, invalid cutoff/timezone, unsafe or replaced paths, unknown/malformed journal, invalid/missing/gapped sequence metadata, missing/unreliable event time, pending or failed persistence, read/replace/fsync failure, and changed journal. Reasons are explanatory fields; existing `deleted`, `skipped`, and `failed` outcomes and final eligibility checks remain authoritative. |
| Summary/recovery | `RoundRetentionStore` carries the App-event cleanup result, reason record, counts, run linkage and diagnostics through the existing ledger summary and recovery path. The fresh coordinator reads the saved result; no plans, journal, retired serials or recovery progress are reset. |
| Deadline race | The final deletion callback rechecks the current global retention period against the event's original timestamp before replace. If an extension makes an event ineligible during the scan, the outcome is recorded as skipped with `app_events_period_changed`; the journal remains unchanged. This preserves the pre-existing “revalidate immediately before deletion” rule. |
| Display | Existing Settings cleanup summary and App diagnostics paths render the captured reason through C1's public presentation contract. English and Traditional Chinese use the same stored record; raw diagnostic and original identifiers/timestamps/counts stay available. C3 does not claim C4's removal of every legacy screen compatibility path. |

## Acceptance evidence

| C3 acceptance | Evidence and result | Limit |
| --- | --- | --- |
| 1. Success, skipped, failure and live-state producer reasons use C1 | `tests.test_app_event_store` covers deletion, no journal, not expired, invalid/unknown/corrupt store, unsafe path/symlink, pending saves and durability/write failure. `tests.test_round_retention` covers public cleanup summaries, failure recovery and retention-period race. | This migrates the App-event producer only. |
| 2. Same-run reason, parameters, bilingual capture, diagnostics, counts and sequence linkage persist | Public `RoundCoordinator` test writes a real temporary App journal, runs cleanup, reads the persisted ledger with a new coordinator and verifies reason id/parameters, captured `en`/`zh-TW`, deleted/skipped counts, serial-retirement linkage and run association; App cleanup does not invent a round id. | New summary bytes are expected output; protected pre-existing bytes are assessed separately. |
| 3. Original timestamp and global retention; pending, failed, unknown and corrupt data stay protected | App-event store tests exercise source event timestamps and cutoff boundary, pending/failed persistence, corrupt and unsupported journal protection. The round-retention race test extends the period after scan and before replace and verifies skipped outcome plus retained event. | No retention policy or time semantics changed. |
| 4. Serial retirement, managed-root/pin, symlink/replacement, atomic replace and fsync remain | Existing public store safety and durability tests were retained and run, including symlink refusal, target change, mixed remaining events/retired ranges, atomic replacement, and fsync failure. Structured reasons are asserted independently of outcomes. | No claim that display metadata participates in safety decisions. |
| 5. Existing background cleanup and summary recovery are reused | Existing coordinator cleanup/retry path writes one summary; injected journal replacement failure remains a failed cleanup with source bytes intact and reason/diagnostic recoverable from a fresh reader. Retention-extension race remains skipped rather than failed or deleted. | No scheduler, journal, or worker was added. |
| 6. Real journal → cleanup → summary → fresh reader → actual screen | Real temporary journal/ledger and fresh coordinator evidence passes. The two focused actual-Tk tests had passed earlier on commit `14c83fa` when the desktop session was usable. On the final code at `fffe809`, both focused Tk tests were retried and the required full suite was retried; all aborted before test bodies at `tests/test_log_solution_ui.py:483` while constructing `tkinter.Tk()`. | Final-code visible-screen evidence must be rerun in a functioning macOS AppKit desktop. This required gate is not marked passed. |
| 7. Expiry, pending/corrupt/path/fsync/retry cases preserve old results | Focused store and retention tests cover not-expired and inclusive deadline behavior, malformed/unknown journal, pending/write failure, symlink/path safety, fsync failure/recovery, and changed-retention revalidation. A fixed-base comparison worktree was run with the same full suite; the final C3 suite passes. | No deletion-qualification changes were made. |
| 8. Old summaries remain unchanged and round reasons remain compatible | C1's mixed legacy/structured ledger read test and C2's round/archive producer evidence remain in the ancestry. C3 adds optional App-event reason data to the existing summary. True-Tk readers compare ledger bytes before/after reading and language switching; old source and protected files are not rewritten. | C2 is not a C3 dependency; its earlier reason records remain readable. C4 remains pending. |

## Test and runtime record

Interpreter: `/opt/anaconda3/bin/python3`, Python 3.11.7; Tk/Tcl 8.6. The current runner did not have a usable macOS AppKit/Tk desktop session, as shown by the native crash evidence below. There is no repository type-check configuration or command in the Python project; no checker was added.

Latest focused store/coordinator checks on final code: `PYTHONPATH=src /opt/anaconda3/bin/python3 -m unittest tests.test_app_event_store tests.test_round_retention -q` — 55 tests, OK (9.649 seconds). The recovery tests verify both that uncertain durability remains pending until journal revalidation and that a legitimate deadline-change `skipped` result remains `complete/skipped` with its original reason after a fresh coordinator reads the ledger. Earlier focused actual-Tk cleanup checks passed 2 tests on commit `14c83fa`; the final code's retry was blocked before the tests could run, as described below.

The required full suite was rerun against the latest code `4cb353f` on 2026-10-13 at 12:00 Asia/Taipei. The command was:

```text
B518_TK_TESTS=1 PYTHONFAULTHANDLER=1 PYTHONPATH=src \
  /opt/anaconda3/bin/python3 scripts/run_tests.py
```

Runtime was Python 3.11.7 / Tk 8.6. The process exited **134** at 12:00:04 during UI test class setup at `tests/test_log_solution_ui.py:483`, before the Tk-dependent test cases ran. macOS logged `Connection Invalid error for service com.apple.hiservices-xpcservice`; AppKit raised `NSInternalInconsistencyException: Invalid parameter not satisfying: aString != nil`. The native stack reaches `NSMenuItem initWithTitle` → Tk `TkpSetMainMenubar` → `_tkinter.create` → `tkinter.Tk()`. The attempt is recorded as a failure, not a pass. Re-running the two C3-specific Tk tests on the same final code also failed at the same `tkinter.Tk()` setup with exit 134. No test-selection, mock, or runtime bypass was used.

Historical context only: an earlier C3 version at `cdaa1dd` passed 397 tests / 132.210 seconds, while the fixed base passed 394 tests / 133.033 seconds. Those runs predate the final durability-recovery hardening and do not satisfy the final-code full-suite gate. The fixed-base and earlier C3 `Tcl_AsyncDelete` aborts remain documented elsewhere in the work history; neither replaces the current AppKit failure. To unblock, rerun the exact full-suite command on a macOS desktop session where a standalone `tkinter.Tk()` can create and destroy its root window, then rerun focused C3 Tk tests and verify the cleanup summary/retry in the actual App.

After the recovery fix in `4cb353f`, `scripts/compare_app_event_retention.py` was rerun against the fixed-base source and final candidate using isolated temporary journals. Both produced the same mixed result (2 deleted, 1 skipped, 0 failed; remaining sequence `[3]`; retired range `[1,2]`; next sequence 4), the same not-expired result (0 deleted, 1 skipped, sequence 1 retained), the same corrupt-store protection (0 deleted, 1 skipped, bytes unchanged), and the same path-swap refusal (0 deleted, 1 failed, original managed path retained and external target unchanged). The script reported `PARITY: identical deletion/retention/count/sequence results`.

## Review and delivery status

Fixed Standards/Spec review base: `f80e86a51907988613185155ed69552c9f392426`. Standards review through `14c83fa` found no blocking findings; its indentation and evidence whitespace suggestions were fixed. The Spec review identified that a legitimate final-gate `skipped` result could retain a pre-replace intent and be rewritten to `failed` during fresh-reader reconciliation. Commit `4cb353f` adds a regression through the public cleanup/fresh-reader path and removes that intent from a known skipped final result; 55 focused tests pass and the required full suite was attempted on this commit, but the Tk/AppKit setup aborted as recorded above. Re-run both fixed-base reviews on the final code/docs before delivery. Direct final remote-SHA confirmation remains outstanding.

The C3 branch is not merged. Latest successful push output advanced both Gitea and GitHub ticket refs to `fffe809`; final direct `ls-remote` SHA checks must be recorded after the documentation commit. No remote issue was modified. C3 does not claim C4 screen unification, parent second-item completion, bundle verification or factory/field acceptance. Because final-code full Tk validation is blocked, the branch and worktree must remain for continuation.
