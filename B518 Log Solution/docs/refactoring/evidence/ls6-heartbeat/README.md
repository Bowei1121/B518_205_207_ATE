# LS6 heartbeat acceptance evidence

Ticket: [#92 — LS6：全狀態半秒四格心跳與同列顯示](https://github.com/Bowei1121/B518_205_207_ATE/issues/92)

Run the acceptance check on the logged-in macOS desktop so it uses the real Aqua/Tk window and can save a content-view capture:

```sh
B518_TK_TESTS=1 \
B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/ls6-heartbeat \
PYTHONPATH=src \
/opt/anaconda3/bin/python3 -X faulthandler scripts/run_tests.py \
  test_log_solution_ui.LogSolutionUiTests.test_ls6_real_tk_heartbeat_cycles_blocks_tracks_states_and_cleans_up
```

`window-bounds.json` records the state marker, heartbeat, both locators, the first result cell, all 17 observations from 0 through 15 and wrap to 0, measured transition intervals, state coverage, actionable close-save UI, and the blocked-main-loop sample. `ls6-heartbeat-state-00-en.png` is a native macOS capture of the mapped Tk window. The test additionally checks that all 16 Canvas patterns use only pure black and white, that state changes and actionable close-save UI do not reset the heartbeat, that the counter advances only once after a blocked event loop resumes, and that destroying the root cancels its own scheduled callback while leaving an unrelated Tk callback alone. The actionable close-save UI check holds the public close status at `saving` to keep the real dialog open; actual save workers remain covered by the existing round-close tests.

These are local Tk geometry and rendering samples. They do not establish physical pixels per Tk unit or a remote KVM sampling threshold. LS7 must measure remote capture scale and determine whether either marker group needs enlargement.
