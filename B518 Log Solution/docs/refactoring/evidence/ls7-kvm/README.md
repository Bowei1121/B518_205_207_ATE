# LS7 KVM evidence

Issue: [#93 — LS7：實測顯示契約並交付 Claude 橋接資料](https://github.com/Bowei1121/B518_205_207_ATE/issues/93)

## Result

Remote KVM acceptance is **not passed**. The inspected computer reports only its built-in Intel display. No JetKVM capture device/tool or live JetKVM frame was available in this run. The App repository's saved captures are native Tk content-view / local macOS evidence, not remote KVM captures. Their 2.0 physical-pixel-per-Tk-unit result must not be applied to a remote stream.

This evidence does not claim that remote marker cells meet 12×12 pixels. It also does not claim remote compression tolerance, live/frozen JetKVM behavior, or the state/heartbeat/result occlusion checks. No synthetic or replayed image is counted as a remote measurement.

## Existing local evidence used

- [`../li7-geometry/README.md`](../li7-geometry/README.md): real Tk UI geometry at scaling 1.0 and 1.5, capacities 1, 10, 11, 20, Profile Editor apply/reload, and documented local capture limitations.
- [`../li7-geometry/escalated-desktop-20261019/li7-geometry-matrix.json`](../li7-geometry/escalated-desktop-20261019/li7-geometry-matrix.json): eight measured local scaling/capacity combinations.
- [`../li8-integration/li7-geometry-language-matrix/li7-geometry-matrix.json`](../li8-integration/li7-geometry-language-matrix/li7-geometry-matrix.json): local English and Traditional Chinese rendering across capacities and both Tk scaling values.
- [`../ls6-heartbeat/README.md`](../ls6-heartbeat/README.md): real Tk heartbeat startup pattern, all 16 states, 500 ms cadence, 8-second cycle, state coverage, blocked-loop behavior, and destroy cleanup.
- [`../ls6-heartbeat/ls6-heartbeat-state-00-en.png`](../ls6-heartbeat/ls6-heartbeat-state-00-en.png): one normal local App frame. Replaying this file three times may demonstrate a repeated-frame detector in an offline consumer test, but it is a local replay, not a frozen JetKVM capture.

The complete App-side contract is [`../../KVM_DISPLAY_CONTRACT.md`](../../KVM_DISPLAY_CONTRACT.md); the bridge handoff is [`../../CLAUDE_KVM_HANDOFF.md`](../../CLAUDE_KVM_HANDOFF.md). Machine-readable contract constants are in [`contract.json`](contract.json).

## Measured local timer crop

[`tk-matrix/timer-crop-matrix.json`](tk-matrix/timer-crop-matrix.json) records the actual `monitor_elapsed` widget bounds and matching pixel crop for each combination of Tk scaling (1.0 and 1.5), capacity (1, 10, 11, 20), and language (`en`, `zh-TW`). Each entry includes its full content-view screenshot, dimensions, physical-pixel conversion, font, color, and anchor. Coordinates start at the Tk content-view top-left. These are local macOS captures only; do not use their pixel conversion as a remote KVM scale.

| Capacity | `00:00` bounds (Tk x,y,w,h) | `00:00` crop (pixels x,y,w,h) | `600:00` bounds (Tk x,y,w,h) | `600:00` crop (pixels x,y,w,h) |
| ---: | ---: | ---: | ---: | ---: |
| 1 | `324,516,44,20` | `648,1032,88,40` | `316,516,52,20` | `632,1032,104,40` |
| 10 | `324,704,44,20` | `648,1408,88,40` | `316,704,52,20` | `632,1408,104,40` |
| 11 | `324,731,44,20` | `648,1462,88,40` | `316,731,52,20` | `632,1462,104,40` |
| 20 | `324,731,44,20` | `648,1462,88,40` | `316,731,52,20` | `632,1462,104,40` |

Both languages and both tested Tk scalings produced the same content-view Tk bounds. The local capture used 2 physical pixels per Tk unit. The crop includes the complete label widget, not only glyph ink, so it remains valid for matching `MM:SS` and long-minute samples.

Reproduce the measurement on the macOS desktop with:

```sh
env B518_TK_TESTS=1 B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/ls7-kvm/tk-matrix PYTHONPATH=src .venv-python31210/bin/python -X faulthandler scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_li7_geometry_at_both_scalings_and_all_capacities
```

## Remote acceptance procedure when a real capture source is available

1. Record App build/version, bridge build/version, JetKVM model/firmware, capture dimensions, stream scaling/cropping, compression settings, and capture timestamps. Save original received frames and checksums.
2. Run the merged App and capture the actual received stream, not the App's local screenshot. Measure all four cells in state and heartbeat markers after scaling/compression. Each remote cell must be at least 12×12 pixels. If either group is smaller, enlarge state and heartbeat together, then re-check locators, row rail, result cells, and all pairwise bounding-box intersections before changing the contract version.
3. Capture stable standby, preparing, monitoring, review, completed, and manual-stop-complete states, including capacity/language/scaling samples. Sample every result cell independently.
4. Occlude the state marker, heartbeat marker, and a result cell in three separate runs. Confirm each missing region fails closed independently while visible regions do not stand in for it.
5. Record at least 9 seconds of one-second observations. Verify the 16-state/8-second heartbeat cycle at source cadence and the every-other-state sequence at observer cadence. Include a normal sequence and an actual frozen/stale source sequence with JetKVM timestamps.
6. Report the measured remote minimum cell dimensions and compression/noise distributions. Until those artifacts are recorded, remote pixel and occlusion criteria remain unpassed.

## Local source inspection

The handoff inspected the separate bridge checkout at commit `8f4e9d7e3bb9e4481e937c4fc4df6cc44e8fa6f1`. That checkout declared `round_frame_consumer.CONTRACT_VERSION = "1.1"` and was 63 commits behind its local `origin/main` tracking ref. This is source-snapshot evidence only; it does not identify the currently deployed bridge version.
