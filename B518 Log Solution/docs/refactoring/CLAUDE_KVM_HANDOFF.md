# Claude handoff: Log Solution KVM display contract 1.3

Date: 2026-10-20 (Asia/Taipei)

This is the App-side handoff for LS7 / GitHub issue #93. It supplies the current local display contract to the bridge maintainer. It does not implement, pair, or deploy a bridge.

## Compatibility gate

| Component snapshot | Version | Compatibility |
| --- | --- | --- |
| Log Solution App | `0.1.0` (`VERSION`) | Emits display contract `1.3` |
| Bridge source inspected for this handoff | `B518_JetKVM_Log` commit `8f4e9d7e3bb9e4481e937c4fc4df6cc44e8fa6f1` | `host-app/round_frame_consumer.py` declares `1.1`; its geometry has the old left locator at x=82 and no independent heartbeat |
| Deployed bridge / JetKVM pairing | Unknown | Not verified |

The inspected bridge snapshot cannot safely consume App contract 1.3. Update the bridge consumer before pairing it with this App. The inspected checkout was 63 commits behind its local `origin/main` tracking ref, so its 1.1 declaration describes only that source snapshot; verify current bridge source and deployed binary before making a deployment decision. This handoff does not imply pairing is complete.

## Contract fields

All coordinates below are Tk units relative to the App's `KVM` parent unless identified otherwise. They must not be used as remote pixel coordinates.

| Field | Contract 1.3 value |
| --- | --- |
| State marker | Origin `(250, 0)`, 26×26 Tk units; six state patterns in `KVM_DISPLAY_CONTRACT.md` |
| Heartbeat marker | Origin `(278, 0)`, 26×26 Tk units; 2-unit gap after state marker; 16 binary states, `0000` at startup, +1 every 500 ms, wrap at 15 |
| Marker cell | 10×10 Tk units; 2-unit gap; 2-unit outer quiet zone; black `#000000`, white `#ffffff` |
| Locators | Left `(0, 2)`, right `(320, 2)`, each 22×22; asymmetric 8×8 white inset identifies orientation |
| Row-count rail | Origin `(130, 2)`; two 10×10 cells with 2-unit gap; `B W` one row, `W B` two rows |
| Result strip | First cell `(0, 34)`; 34×26 Tk units; 10 columns; row step 27; capacity 1–20 |
| Timer | Outside the KVM band, in `monitor_status_row`; bold Menlo, current font size 14; right-aligned `MM:SS`, unlimited minutes |
| Result colors | PASS `#00ef00`; FAIL `#ff0000`; TESTING `#ffff00`; NOTEST `#f04bf1`; WAITING `#d9d9d9`; COMPLETING `#82c7ff`; STALLED/TIMEOUT `#ff9900`; STOPPED `#bfbfbf`; capacity-external cells `#000000` |
| Local marker sample gate | Grayscale 0–80 black, 176–255 white, 81–175 unknown; locators must confirm orientation first |

The App timer measures time since monitoring acceptance, including source preparation, and stops when collection stops. It is evidence of the start flow being accepted only; it does not establish source readiness or ATE activity. `PREPARING` means the source baseline is not ready. `MONITORING` means Log Solution can collect new round data, not that the ATE has started. A deliverable result requires a completed or manual-stop-complete pattern plus terminal result cells and no pending review. The App contract defines state precedence.

## Sampling handoff for Claude to validate

At a nominal one-second observation cadence, the anomaly decision is about the heartbeat region only:

1. Count only distinct, fresh observations whose heartbeat region is fully visible and readable. An old/reused frame, occluded region, or uncertain compression sample is invalid and cannot be one of the three. Freshness uses source presentation timestamps or equivalent capture freshness evidence; permitted timestamp gaps remain for Claude to decide.
2. Compare the four-cell heartbeat-region image only. If the same readable heartbeat-cell image persists for three consecutive valid observations, report the heartbeat as abnormal. At one observation per second, the first-to-third span is about two seconds. Timer, state, result, and other pixels may change and do not cancel this rule.
3. Reject compression noise as heartbeat movement. Compare valid cell appearance across the heartbeat crop without decoding the four cells into a 0–15 number. Remote compression tolerance has not been calibrated, so the local 0–80 / 176–255 gate is not a certified stream threshold.
4. In healthy operation the App advances one state every 500 ms and wraps after 16 states (8 seconds). `+2 mod 16` is an explanatory expected cadence for one-second observations only; it is not an extra decoding requirement and does not replace the three-identical-heartbeat-region anomaly rule.
5. A whole-frame identical replay can be retained as a separate stale-frame fixture. It is not required for detecting an unchanged heartbeat region, and three whole-frame-identical captures are not required when unrelated pixels change. Maximum observation interval, interruption reset, recovery threshold, and upper-computer error handling remain open decisions for Claude.

Validate at least these cases: an old timer value still visible in standby before a new round; accepted start with timer advancing while state is `PREPARING`; transition to `MONITORING`; normal timer stop while heartbeat keeps advancing; quick completion before a two-second stable-state window; a deliverable result; and pending review. Timer movement alone must never be treated as ATE activity or a deliverable result.

Occlusion must be tested independently for the state marker, heartbeat marker, and each required result cell. The top locators do not prove the result strip is visible. Keep the result cells, locators, and markers at their existing positions unless a real remote measurement shows a failure and a coordinated marker resize is measured to avoid overlap.

## Local timer crop

The companion `evidence/ls7-kvm/tk-matrix/timer-crop-matrix.json` records the current merged App's live Tk widget bounds and reproducible crop ROI for `00:00` and `600:00`, across Tk scaling 1.0/1.5, capacity 1/10/11/20, and English/Traditional Chinese. Each ROI is pixel coordinates relative to its named native content-view screenshot, derived from that capture's measured pixel-to-content-view scale. These are local capture coordinates, not remote KVM pixel coordinates. The JSON points to both normal and long-minute full-window captures and records the timer font, foreground, anchor, widget bounds, and screenshot dimensions.

## Evidence and release status

The local scale/capacity/language matrix and real Tk screenshots are listed in [`evidence/ls7-kvm/README.md`](evidence/ls7-kvm/README.md). They establish local App rendering only. This machine had no attached external display or discoverable JetKVM capture tool during the LS7 run. No real JetKVM frame was available, so remote per-cell pixel size, remote compression tolerance, and the three separate occlusion checks remain unpassed. Do not infer them from Retina content-view scale or generated/replayed local images.

No files in `B518_JetKVM_Log`, TCP code, or LabVIEW are changed by this ticket. This document is handoff data only; bridge pairing and deployment remain future work.
