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

At a nominal one-second observation cadence:

1. Reject a sample unless both locator patterns, orientation, and every required marker cell are readable with the local high-contrast gate. The gate is a starting value, not remote calibration.
2. Treat three consecutive valid observations with the same decoded state and unchanged result/layout snapshot as a stable-state window. At exact one-second spacing, the first-to-third span is about two seconds.
3. The heartbeat should advance by `+2 mod 16` between observations. Full-image byte identity is not a healthy-frame definition because heartbeat changes every 500 ms and the timer may change. Three byte-identical captures instead indicate a stale/frozen candidate.
4. A full heartbeat cycle is 16 transitions × 0.5 seconds = 8 seconds. A one-second observer sees every other state, so its observed sequence repeats after eight seconds.
5. Do not trust a repeated old frame as fresh evidence. Presentation-timestamp freshness, compression tolerance, maximum observation interval, interruption reset, recovery threshold, and upper-computer error handling remain open decisions for Claude. Do not present these decisions as finalized by LS7.

Validate at least these cases: an old timer value still visible in standby before a new round; accepted start with timer advancing while state is `PREPARING`; transition to `MONITORING`; normal timer stop while heartbeat keeps advancing; quick completion before a two-second stable-state window; a deliverable result; and pending review. Timer movement alone must never be treated as ATE activity or a deliverable result.

Occlusion must be tested independently for the state marker, heartbeat marker, and each required result cell. The top locators do not prove the result strip is visible. Keep the result cells, locators, and markers at their existing positions unless a real remote measurement shows a failure and a coordinated marker resize is measured to avoid overlap.

## Evidence and release status

The local scale/capacity/language matrix and real Tk screenshots are listed in [`evidence/ls7-kvm/README.md`](evidence/ls7-kvm/README.md). They establish local App rendering only. This machine had no attached external display or discoverable JetKVM capture tool during the LS7 run. No real JetKVM frame was available, so remote per-cell pixel size, remote compression tolerance, and the three separate occlusion checks remain unpassed. Do not infer them from Retina content-view scale or generated/replayed local images.

No files in `B518_JetKVM_Log`, TCP code, or LabVIEW are changed by this ticket. This document is handoff data only; bridge pairing and deployment remain future work.
