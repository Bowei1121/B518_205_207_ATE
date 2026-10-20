# KVM display contract 1.3

This is the local Log Solution display contract. It defines the Tk status band that a separate consumer may inspect. It does not define or implement a transport protocol, KVM recognition, or an ATE control path. A consumer must update with the App because version 1.3 adds an independent heartbeat marker and moves the state marker; a version 1.2 consumer cannot safely interpret every 1.3 frame.

## Coordinate spaces and geometry

Coordinates are Tk units relative to the `KVM` parent frame. They are not physical pixels. On the verified macOS desktop, the Tk content view rendered at 2.0 physical pixels per Tk unit; consumers must measure their own capture scale and must not infer it from Tk scaling or assume that it applies to remote captures.

| Element | Tk geometry | Purpose |
| --- | --- | --- |
| Left locator | origin `(0, 2)`, 22×22; white 8×8 inset at `(3, 3)` | Orientation/scale anchor above the first strip cell |
| Row-count rail | origin `(130, 2)`, 26×14; two 10×10 cells with a 2-unit gap | `B W` = one row; `W B` = two rows |
| State marker | origin `(250, 0)`, 26×26 | Four-cell state pattern |
| Heartbeat marker | origin `(278, 0)`, 26×26 | Independent four-cell binary counter |
| Right locator | origin `(320, 2)`, 22×22; white 8×8 inset at `(11, 11)` | Opposite asymmetric orientation anchor |
| Result cells | first row y=34; 34×26 cells; 27-unit row step | Ten fixed columns; second row for positions 11–20 |

The parent frame is 360 Tk units wide. The first result cell begins at x=0; the left locator is fully inside the parent and starts at x=0, so rendering does not rely on negative Canvas coordinates or clipping. The parent has a 2-unit top inset, 338-unit right inset, and 37-unit bottom inset for capacities 1–10 or 64-unit bottom inset for capacities 11–20. In the main window the parent begins 8 Tk units from the Tk content's left edge. The left locator's inset is asymmetric: its white cell is 3/3/11/11 units from the left/top/right/bottom edges; the right locator retains the opposite `(11, 11)` inset. The locators are 320 units apart.

The state and heartbeat markers share a row and size, separated by a 2-Tk-unit gap. The heartbeat ends at x=304, leaving 16 Tk units before the right locator at x=320. Both locators and every result cell retain their prior coordinates.

Each row always has ten cells. Capacity 1–10 displays one row; capacity 11–20 displays two. Unused capacity cells stay black. The row rail is rendered from the same frozen snapshot/capacity as the strip. It is independent of result availability. A top marker cannot detect every occlusion: a separate window covering only a result strip while leaving the upper locator visible may evade locator-based occlusion checks. Consumers must still validate each required result cell.

## Six state patterns

Rows are top-to-bottom, columns left-to-right. `B` is `#000000`; `W` is `#ffffff`. The pattern table is owned by `src/kvm_display_contract.py` and `classify_kvm_frame_samples` returns unknown for missing, low-contrast, reversed-locator, or unlisted samples.

| State | Pattern | Snapshot meaning |
| --- | --- | --- |
| STANDBY | `B W / W B` | No released current round, including not started, start failure, or cancelled round |
| PREPARING | `W B / W B` | Start accepted; source baseline/preparation is still pending; ATE must not start |
| MONITORING | `B B / W W` | Source preparation is complete; new round data can be collected |
| REVIEW | `B W / B W` | Conflict, unacknowledged alarm, or start failure requires operator action |
| COMPLETE | `W B / B W` | State is completed, full results are available, and no confirmation is pending |
| MANUAL_STOP_COMPLETE | `W W / B B` | A manually stopped round has full results available and no confirmation pending |

Review has priority over every released state. Monitoring is not proof that the ATE has started; only trusted channel activity or a valid result provides that evidence. Complete is not equivalent to all PASS: FAIL, NOTEST, TIMEOUT, or STOPPED may be part of a complete result. Closing a review window does not acknowledge it. A fresh round is required before a prior released result can be treated as current-round output.

The classifier first validates both asymmetric locator samples, then the four state-cell samples. Its grayscale thresholds are part of the local helper; they are a minimum sample-quality gate, not a validated tolerance for remote compression, perspective, occlusion, or JetKVM capture.

## Independent heartbeat

The heartbeat is four 10×10 Tk-unit cells with 2-unit gaps and a 2-unit quiet zone, matching the state marker's 26×26 geometry. Bits are read top-to-bottom and left-to-right; `0` is white (`#ffffff`) and `1` is black (`#000000`). It starts at binary `0000`, advances by one every 500 ms, and wraps from `1111` to `0000`:

| Decimal | Binary | Cells, top row / bottom row (`W` = white, `B` = black) |
| ---: | :---: | :--- |
| 0 | `0000` | `W W / W W` |
| 1 | `0001` | `W W / W B` |
| 2 | `0010` | `W W / B W` |
| 3 | `0011` | `W W / B B` |
| 4 | `0100` | `W B / W W` |
| 5 | `0101` | `W B / W B` |
| 6 | `0110` | `W B / B W` |
| 7 | `0111` | `W B / B B` |
| 8 | `1000` | `B W / W W` |
| 9 | `1001` | `B W / W B` |
| 10 | `1010` | `B W / B W` |
| 11 | `1011` | `B W / B B` |
| 12 | `1100` | `B B / W W` |
| 13 | `1101` | `B B / W B` |
| 14 | `1110` | `B B / B W` |
| 15 | `1111` | `B B / B B` |

Tk's main event loop owns the only heartbeat schedule. If that loop is blocked, the marker freezes; after it resumes, the counter advances once and does not replay missed ticks. The counter is independent of round timer, round acceptance, source work, and close-save progress. It remains active for the root lifetime, including standby, preparing, monitoring, review, completed, start-failure reset, and actionable close-save states. Destroying the root cancels the heartbeat's owned callback. Heartbeat changes do not append permanent events.

## Local verification artifacts

The LS6 heartbeat acceptance evidence is in `evidence/ls6-heartbeat/README.md`, including real Tk frame samples, timing, state coverage, and destroy cleanup. The earlier geometry matrix is documented in `evidence/li7-geometry/README.md`; it covers Tk scaling 1.0 and 1.5, capacities 1/10/11/20, Profile Editor apply/reload, widget bounds, capacity-external black cells, and Tk content-view captures. These captures are native App/Tk rendering, not remote KVM evidence. Local Tk geometry and scaling do not establish remote pixels per Tk unit. Remote pixel thresholds and any required marker enlargement remain unmeasured and belong to LS7's physical KVM measurements.

## Compatibility and scope

Version 1.1 predates the left locator at x=0 and has no PREPARING or MANUAL_STOP_COMPLETE state. Version 1.2 does not include the heartbeat marker. Their samples and consumers remain historical and are not rewritten as 1.3 evidence. Do not send version 1.3 frames to an older consumer as if the versions were compatible. The `B518_JetKVM_Log` project owns its own recognition and bridge behavior; `monitor_start`, `check_start`, and `check_finish` are implemented there. Log Solution does not add TCP commands, ACK handling, JetKVM recognition, Dock automation, LabVIEW behavior, or field ATE validation.

## LS7 handoff status (2026-10-20)

Version 1.3 is the frozen **App-side local contract** for the merged timer and heartbeat behavior. It is not a remotely validated pixel contract. See [`CLAUDE_KVM_HANDOFF.md`](CLAUDE_KVM_HANDOFF.md) and [`evidence/ls7-kvm/README.md`](evidence/ls7-kvm/README.md) for the consumer handoff and evidence status. The 12×12 remote-pixel threshold has not been measured, so the available evidence does not justify enlarging either marker.

The monitoring timer is outside the `KVM` result-band frame. It is the right-aligned `monitor_elapsed` label in `monitor_status_row`, rendered in bold Menlo at `MAIN_FONT_SIZE` (currently 14 Tk points). Its text is `MM:SS`: seconds are `00–59`, minutes have a minimum width of two digits and continue without an upper limit, with no hours field or sub-second digits. The label width follows its rendered text. Measured local widget bounds and crop ROIs for `00:00` and `600:00`, across capacity, language, and Tk scaling, are in `evidence/ls7-kvm/tk-matrix/timer-crop-matrix.json`. Each ROI is relative to its linked native content-view capture. These local measurements do not define remote capture coordinates.

App-side marker classification uses grayscale threshold 128 with a 96-level minimum contrast: black samples are at most 80 and white samples at least 176; values between them are unknown. These are local helper defaults, not remote compression tolerances. Result-cell colors are defined in `src/b518_log_solution.py`; the machine-readable values and sample matrix are in the LS7 handoff evidence. Remote color tolerances remain unvalidated.

At a nominal one observation per second, compare the heartbeat region only. Three consecutive distinct, fresh, readable observations with the same heartbeat-cell image are the abnormal condition; the first-to-third span is about two seconds. Old/reused frames, an occluded crop, or compression-uncertain samples are invalid and do not count. Changes in timer, state, results, or other pixels do not cancel an unchanged-heartbeat finding. Compare readable cell appearance without decoding the four cells into a 0–15 number. The healthy `+2 mod 16` cadence is explanatory, not a replacement rule or decoding requirement. Whole-frame replay detection is a separate optional stale-frame check. Remote freshness and compression tolerances still need validation against real JetKVM frames.
