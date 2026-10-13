# C3 local validation — App-event cleanup reasons

Date: 2026-10-13 (Asia/Taipei)
Ticket: cleanup-reason C3, GitHub #35 (parent #28)
Branch: `LanguageRefresh/ticket-07`
Fixed review base: `f80e86a51907988613185155ed69552c9f392426`
Code commits: `4e19cd608d20362feaeb96912c8a277e955d11af`, `cdaa1ddf6a9f12d25ef5fd90c901ef97c5a8c534`, `373da606bc60516db3a91c678485a3f8417c7ec4`, `e1b4e3ac0f84c1c9a8d146d579c3170b82dc893a`, `cd1fc76aae1892947c63bc948d6cbc666b6c0667`, `34c38112232033e52985b616584a56a20b2eac08`, `14c83faae1b556a8f1bd051e339046e82d6f2f4d`, `fffe809`, `4cb353f`, `7639be8b8af1fb77461706d763ae95402ae3a3cc` (final code/test commit)

## Final acceptance update (2026-10-13)

Final code/test SHA: `7639be8b8af1fb77461706d763ae95402ae3a3cc`. Required desktop suite passed **404 tests / 140.160 seconds / exit 0**, with Python 3.11.7 at `/opt/anaconda3/bin/python3`, Tk/Tcl 8.6, outside the sandbox so macOS GUI services are accessible. Command: `B518_TK_TESTS=1 PYTHONFAULTHANDLER=1 PYTHONPATH=src /opt/anaconda3/bin/python3 -u scripts/run_tests.py`, from `B518 Log Solution/`. Complete output: [desktop-suite-final.log](desktop-suite-final.log).

The previously failing startup cleanup-summary test passes on this final code. A public fresh-reader regression first failed (`failed` versus `complete`) and now preserves completed status, the captured run-summary reason, run/time linkage and unchanged ledger bytes. The fix durably saves the complete result with its recovery receipt before removing that receipt and synchronizing again. If receipt-retirement directory fsync fails, the original failed/pending path retains the same run, deletion sequences and bilingual evidence; safe retry does not credit a second deletion. Focused App store/coordinator tests pass **56 tests / 9.513 seconds**. Fixed-base/candidate deletion, retention, count and sequence parity was rerun and remains identical.

Final fixed-base Standards/Spec reviews on this code have no unresolved blockers. Standards has one non-blocking naming suggestion about the private-definition/public-alias error type; Spec independently passed three durability/deadline recovery tests. Eight C3 acceptance items have final-version evidence. Pre-merge documentation review, post-merge full desktop suite and direct destination/cleanup verification are recorded in the delivery addendum when executed. Earlier failures below are historical and are superseded by this final-code pass; they are retained to distinguish the sandbox abort from the real fresh-reader regression and its fix.

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
| 6. Real journal → cleanup → summary → fresh reader → actual screen | Final full desktop suite passes `test_real_tk_shows_startup_cleanup_summary_after_disk_deletion`, `test_real_tk_app_event_cleanup_failure_is_visible_and_retryable`, timezone-missing protection/presentation, and mixed-ledger raw-read/byte-preservation cases. These use isolated real journals/ledgers, real Tk widgets and new public readers. | C3 screen evidence is source-App acceptance; it does not claim native OS title-bar or independent equipment/bundle acceptance. |
| 7. Expiry, pending/corrupt/path/fsync/retry cases preserve old results | Focused store and retention tests cover not-expired and inclusive deadline behavior, malformed/unknown journal, pending/write failure, symlink/path safety, fsync failure/recovery, and changed-retention revalidation. Fixed-base/candidate public cleanup fixtures give identical deletion/retention/count/sequence results; the full desktop suite result is recorded below. | No deletion-qualification changes were made. |
| 8. Old summaries remain unchanged and round reasons remain compatible | C1's mixed legacy/structured ledger read test and C2's round/archive producer evidence remain in the ancestry. C3 adds optional App-event reason data to the existing summary. True-Tk readers compare ledger bytes before/after reading and language switching; old source and protected files are not rewritten. | C2 is not a C3 dependency; its earlier reason records remain readable. C4 remains pending. |

## Historical attempts and runtime diagnosis

Interpreter: `/opt/anaconda3/bin/python3`, Python 3.11.7; Tk/Tcl 8.6. Sandboxed execution could not access the macOS AppKit/Tk desktop services. The later sandbox/outside-sandbox pair below establishes that this was an execution restriction rather than evidence that the desktop itself was unavailable. There is no repository type-check configuration or command in the Python project; no checker was added.

Earlier focused store/coordinator checks before receipt-retirement fix: `PYTHONPATH=src /opt/anaconda3/bin/python3 -m unittest tests.test_app_event_store tests.test_round_retention -q` — 55 tests, OK (9.649 seconds). The recovery tests verify both that uncertain durability remains pending until journal revalidation and that a legitimate deadline-change `skipped` result remains `complete/skipped` with its original reason after a fresh coordinator reads the ledger. Earlier focused actual-Tk cleanup checks passed 2 tests on commit `14c83fa`; the final code's retry was blocked before the tests could run, as described below.

The required full suite was rerun against the latest code `4cb353f` on 2026-10-13 at 12:00 Asia/Taipei. The command was:

```text
B518_TK_TESTS=1 PYTHONFAULTHANDLER=1 PYTHONPATH=src \
  /opt/anaconda3/bin/python3 scripts/run_tests.py
```

Runtime was Python 3.11.7 / Tk 8.6. The process exited **134** at 12:00:04 during UI test class setup at `tests/test_log_solution_ui.py:483`, before the Tk-dependent test cases ran. macOS logged `Connection Invalid error for service com.apple.hiservices-xpcservice`; AppKit raised `NSInternalInconsistencyException: Invalid parameter not satisfying: aString != nil`. The native stack reaches `NSMenuItem initWithTitle` → Tk `TkpSetMainMenubar` → `_tkinter.create` → `tkinter.Tk()`. The attempt is recorded as a failure, not a pass. Re-running the two C3-specific Tk tests on the same final code also failed at the same `tkinter.Tk()` setup with exit 134. No test-selection, mock, or runtime bypass was used.

### Requested retest (2026-10-13 12:08 Asia/Taipei)

The complete command above was run again on clean ticket HEAD `9fa4d0a2f6a33e233c29e8279eb23c6abff7c39e` from the Python project directory with `/opt/anaconda3/bin/python3` (Python 3.11.7; Tk/Tcl 8.6). Non-Tk tests began and passed, then the process again aborted with exit **134** in `tests/test_log_solution_ui.py:483` while `setUpClass` constructed `tkinter.Tk()`. The Tk-dependent test bodies did not run. This confirms the full-suite gate remains blocked by native Tk/AppKit startup in this execution session; no code or test selection was changed for the retest.

Historical context only: an earlier C3 version at `cdaa1dd` passed 397 tests / 132.210 seconds, while the fixed base passed 394 tests / 133.033 seconds. Those runs predate the final durability-recovery hardening and do not satisfy the final-code full-suite gate. The fixed-base and earlier C3 `Tcl_AsyncDelete` aborts remain documented elsewhere in the work history; neither replaces the current AppKit failure. To unblock, rerun the exact full-suite command on a macOS desktop session where a standalone `tkinter.Tk()` can create and destroy its root window, then rerun focused C3 Tk tests and verify the cleanup summary/retry in the actual App.

After the recovery fix in `4cb353f`, `scripts/compare_app_event_retention.py` was rerun against the fixed-base source and final candidate using isolated temporary journals. Both produced the same mixed result (2 deleted, 1 skipped, 0 failed; remaining sequence `[3]`; retired range `[1,2]`; next sequence 4), the same not-expired result (0 deleted, 1 skipped, sequence 1 retained), the same corrupt-store protection (0 deleted, 1 skipped, bytes unchanged), and the same path-swap refusal (0 deleted, 1 failed, original managed path retained and external target unchanged). The script reported `PARITY: identical deletion/retention/count/sequence results`.

## Historical pre-acceptance review and delivery status

Fixed Standards/Spec review base: `f80e86a51907988613185155ed69552c9f392426`. Final paired reviews completed on `79a85199f462034ca83c4959342716924153d307` against that fixed base. Standards found no documented-rule breach or blocking smell; prior indentation and evidence whitespace suggestions are fixed. Its only note is a non-blocking naming observation about the private definition/public alias of `AppEventCleanupError`. Spec confirmed commit `4cb353f` preserves a deadline-extension `skipped` result through a fresh reader and that uncertain post-replace durability still retains its recovery intent; no other implementation defect or scope creep was found. The reviewer reran three focused recovery/deadline tests successfully; the broader focused suite has 55 passing tests. Both reviewers agree the required final full Tk suite and visible-screen acceptance remain blocked by the AppKit startup abort.

At that checkpoint the C3 branch was not merged. After pushing documentation commit `8e6bd773d968b08814f49e0249a541bb3f7cdd14`, direct `git ls-remote` queries at 2026-10-13 12:05:56 Asia/Taipei confirmed both the Gitea and GitHub `LanguageRefresh/ticket-07` refs at that SHA; both `B518-Log-Solution` refs remained at `f80e86a51907988613185155ed69552c9f392426`. This query is direct remote evidence, not a tracking-ref inference. No remote issue was modified. C3 does not claim C4 screen unification, parent second-item completion, bundle verification or factory/field acceptance. The branch and worktree were retained until the subsequent final-code desktop validation above resolved this gate.


## Diagnosis update: sandbox distinguished from a real assertion failure

On 2026-10-13, a minimal program using the same Python 3.11.7/Tk 8.6 created, updated, verified and destroyed a Tk root without importing B518 code. Sandboxed execution reproduced `NSInternalInconsistencyException: aString != nil` and exit 134; the same command outside the sandbox printed `Tk create/update/destroy PASS` and exited 0. Earlier claims that the desktop environment was unavailable were too broad: access to macOS GUI services was restricted by the sandbox.

The required full suite was then executed outside the sandbox against `e4d2ba71ad5cf345afa0f0aa03e52bc6a5992af7`, using the same command/runtime and isolated test data. It completed **403 tests / 126.985 seconds / exit 1 / one failure**, without the native startup abort. C3 cleanup failure/retry, missing-timezone presentation, and mixed-ledger Tk cases passed. The failure was:

```text
FAIL: test_real_tk_shows_startup_cleanup_summary_after_disk_deletion
tests/test_log_solution_ui.py:1752
expected: app.settings.retention.reason.cleanup.run_summary
actual:   app.settings.retention.reason.cleanup.interrupted
```

The successful cleanup's persisted final row still carries `app_event_commit_intent`; `_summary_from_dict` interprets a complete row with that marker as durability awaiting revalidation and changes its presentation to interrupted. Thus the live coordinator reports completion while the fresh reader does not reconstruct the same completed summary. That revision had a concrete C3 regression/acceptance blocker. The subsequent final-code fix and desktop pass above resolve it without weakening uncertain replace/fsync protection; the failed run and diagnosis are retained as historical evidence. No code or assertions were changed during that diagnosis.


## Post-merge verification and delivery

All eight C3 acceptance items and the final fixed-base Standards/Spec documentation reviews passed at pre-merge documentation SHA `509800011496e90fbd6aabf23a68f90bbdaa10e7`; no code changed after `7639be8b8af1fb77461706d763ae95402ae3a3cc`. Before integration, direct queries and fetches found both GitHub and Gitea mainline refs at fixed base `f80e86a51907988613185155ed69552c9f392426`, both ancestors of the ticket.

The mainline worktree's pre-existing `PROJECT_SUMMARY_2026-10-09.md` and `PROJECT_SUMMARY_2026-10-12.md` changes were copied to a private temporary backup with SHA-256 hashes and temporarily stashed by explicit paths. The target worktree was checked clean before `git merge --ff-only LanguageRefresh/ticket-07`. Integration was a **fast-forward** to `509800011496e90fbd6aabf23a68f90bbdaa10e7`, not a new merge commit.

From the mainline Python project directory, the same authorized desktop command was rerun: **404 tests / 133.908 seconds / exit 0**. Raw output: [desktop-suite-postmerge.log](desktop-suite-postmerge.log). Both final logs contain no Tcl_AsyncDelete, ignored Tk destructor exception or residual invalid-command callback. This post-merge pass covers the same final code, actual App/Tk summary/diagnostic/retry and disk-rebuild cases as the ticket pass. There is no configured type-checking command.

Final source-App acceptance is complete. C1 is in the fixed-base ancestry with final validation evidence; C2 already in that baseline retains its round/archive contract. C3 changes only the App-event producer and necessary local screen use of C1's reason contract. C4 complete screen consolidation, parent second-item completion, formal bundle and factory/field verification remain separate. No issue was published, edited or closed. Destination synchronization and cleanup are recorded below after execution.


### Synchronization, cleanup and protected changes

Post-merge validation/documentation commit: `e13060fff25d89b5ed630f09ce0421e20f771734`. At 2026-10-13 13:01:53 Asia/Taipei, direct `git ls-remote` queries confirmed both GitHub and Gitea mainline and ticket refs at this SHA. Only after that confirmation, the already-merged `LanguageRefresh/ticket-07` remote branch was deleted at both existing push destinations, its clean local worktree `/private/tmp/B518-LanguageRefresh-C3` was removed without force, its clean C3 comparison worktree `/private/tmp/B518-C3-baseline` was removed without force, and the local ticket branch was deleted with `git branch -d`. Before removal, both worktrees had no tracked or untracked changes; their only ignored files were Python test caches.

At 13:03:33, direct queries confirmed both mainline refs still at `e13060fff25d89b5ed630f09ce0421e20f771734`, no remote ticket refs, and no local ticket branch. No other series branch/worktree or push destination was removed. The primary project checkout is on `B518-Log-Solution`. The two pre-existing summary changes were restored and compared byte-for-byte via their backup SHA-256 hashes; only the stash created for this protection was dropped. They remain uncommitted, exactly as before this ticket, and are excluded from all C3 commits.

Final delivery consists of code/test SHA `7639be8b8af1fb77461706d763ae95402ae3a3cc`, fast-forward integration result `509800011496e90fbd6aabf23a68f90bbdaa10e7` (no merge commit), post-merge evidence commit `e13060fff25d89b5ed630f09ce0421e20f771734`, and the final documentation commit containing this cleanup addendum. The final documentation SHA and post-push direct destination confirmation are reported in the delivery response; it changes no code/resources/tests and needs no new bundle. C3 has no remaining acceptance blocker.

Raw log SHA-256:
- `desktop-suite-final.log`: `38f9eb9484bad55eacd5602709a512ad88d74e6691c713aeea1fc96b153457c5`
- `desktop-suite-postmerge.log`: `4239e1bef686e39ec5046a5634124f8401db91ca72b851551ce55e0cbb7119ba`
