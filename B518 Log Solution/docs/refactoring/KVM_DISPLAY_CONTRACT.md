# KVM display contract 1.1

This contract describes the Tk app's machine-readable top band. Ticket 16 upgrades the original Ticket 12 contract 1.0 to 1.1: a row-count rail distinguishes a real single-row layout from an unreadable second row. App and upper computer must update together; a 1.0 frame without this rail is rejected by the 1.1 consumer. Actual JetKVM capture and field deployment remain unverified; local Tk/Quartz frame integration is recorded under evidence/ticket-16/contract-1.1/.

## Coordinate spaces and geometry

All coordinates below are Tk widget coordinate units relative to the `KVM RESULT` frame. They are logical app coordinates, not guaranteed physical display pixels. The frame is laid out in a 376-unit-wide, fixed-width app. A capture system must measure its own physical-pixel-to-Tk-unit scale; it must not assume Retina scale, `tk scaling`, or an arbitrary remote-desktop resize factor. The app's tests use Tk scaling 1.0 and 1.5, but this does not establish remote KVM compatibility.

| Element | Tk geometry | Purpose |
| --- | --- | --- |
| Left locator | origin `(82, 2)`, 22×22; white 8×8 inset at `(3, 3)` | Asymmetric orientation/scale anchor |
| Row-count rail | origin `(130, 2)`, 26×14; two 10×10 cells, 2-unit gap and white quiet margin | `B W` = one row, `W B` = two rows; other patterns reject |
| State marker | origin `(278, 0)`, 26×26 | 2×2 state pattern, no text required |
| Right locator | origin `(320, 2)`, 22×22; white 8×8 inset at `(11, 11)` | Opposite asymmetric orientation/scale anchor |
| Result cell | 34×26, 27-unit row step; first row begins at y=34 | Fixed ten-column product result band |

The row-count rail is independent of the four state patterns and says nothing about result availability. It is drawn from the same frozen capacity as the product band, during the same snapshot-render callback. The one-row consumer samples exactly ten cells; the two-row consumer requires all first-row cells to be in capacity, at least one second-row cell in capacity, and the entire second row visible. Missing, low-contrast or unknown row patterns reject; unknown second-row pixels must never be treated as a valid capacity-ten layout.

The state marker uses a white background and a 2-unit quiet zone. Each black/white cell is 10×10, with a 2-unit horizontal and vertical gap. The locator, state marker, and product band occupy separate regions. For capacity 1–10, the result band is one row of ten cells; for 11–20 it is two rows of ten, with positions 1–10 above 11–20. Capacity-external cells remain black. The marker is above the band and does not use its black cells. Result-cell width and horizontal pitch share one contract constant to keep the UI and stated geometry aligned.

## State patterns

Rows are top-to-bottom and columns left-to-right. `B` is `#000000`, `W` is `#ffffff`. The locators establish orientation; OCR is not part of state recognition.

| State | Top row | Bottom row | Snapshot meaning |
| --- | --- | --- | --- |
| Standby | `B W` | `W B` | No released current round, including not started, start failure, or manual stop |
| Monitoring | `B B` | `W W` | Round is running/preparing with no required confirmation |
| Review | `B W` | `B W` | Conflict or unacknowledged round alarm; collection may continue or be stopped |
| Complete | `W B` | `B W` | Snapshot says COMPLETED and results are available |

Mapping precedence is explicit: (1) any awaiting-review state, pending conflict, or unacknowledged round alarm maps to Review; (2) otherwise, `COMPLETED` plus `result_available` maps to Complete; (3) otherwise, `RUNNING` maps to Monitoring; (4) every other state maps to Standby. Thus no pending confirmation can appear Complete, even if a malformed or transient snapshot also carries `result_available`. Closing a review window does not change the snapshot. The Tk renderer obtains one `RoundSnapshot` and updates result cells and marker during the same UI callback. It redraws the marker only when the state changes to avoid flashing.

## Sampling and rejection limits

Before sampling the four state cells, verify orientation from both asymmetric locators. The public `classify_kvm_frame_samples` helper expects grayscale averages at (in order) the left locator's near white inset, left far black area, right near black area, and right locator's far white inset. Each locator sample must pass the same white (`176–255`) or black (`0–80`) threshold for the expected polarity. Missing, low-contrast, out-of-range, or reversed locator samples produce **unknown** before state classification. Then sample the four marker-cell centers top-left, top-right, bottom-left, bottom-right. Values `0–80` classify as black and `176–255` as white. Values `81–175`, missing cells, out-of-range values, or a four-bit pattern outside this contract produce **unknown**, never Complete. This is a minimum input-quality gate, not a validated remote-image recognizer. Sampling crop size, compression, perspective, occlusion, and inter-frame consistency must be verified by the consumer.

The automated classifier tests exact patterns, orientation rejection, and low-contrast, missing, and unknown samples. Tk tests cover scale settings 1.0 and 1.5 and ensure the marker stays above the result band while twenty detail rows scroll. Actual KVM hardware, transport/compression and remote scaling remain unverified. Ticket 16 has now verified independent raw captures of actual Tk windows for capacities 1/4/6/10/11/12/20 and four-state controlled flows through the upper-computer frame interface; these are local Quartz captures, not JetKVM evidence. Ticket 16 must measure the deployed capture path and repeat the sample recognition against that system.

## Reproducible artifacts

Ticket 12's controlled Tk screenshots and run metadata are stored under `evidence/ticket-12/`. They contain synthetic/anonymized values only and are not actual KVM captures. `tools/smoke_state_marker_app.py` recreates the four states through the app's shared round interface and captures the app window on macOS.

## JetKVM prototype reference

The separate `B518_JetKVM_Log` repository was inspected as a read-only design reference. Its README describes a JetKVM upper-computer prototype that captures a remote frame and performs template matching, while explicitly keeping local Log reading in an independent project with no code dependency. Its `JetKVMClient.frame` stores decoded BGR frames, which gives Ticket 16 a useful measurement point: record the actual frame width/height and compare native capture pixels with this app's Tk-unit geometry. The prototype's multiscale matching diagnostics are a useful investigation pattern, not validation of this marker's recognition thresholds.

That repository's historical FCT image is not a current-device sample and contains no Ticket 12 two-by-two marker contract. It was not copied into this repository or used as acceptance evidence. Ticket 16 must capture the deployed app through the actual JetKVM path and independently validate orientation, physical dimensions, transport/compression, and marker classification.

## Version 1.1 controlled integration

The 2026-10-05 Spec rereview found that the original upper recognizer always sampled twenty cells, although the App hides row two at capacity ten or below. Synthetic frames painted twenty cells for every capacity and hid the fault. TDD reproduced this at the raw-frame/round-gate seam. Version 1.1 adds only the independent row rail; locators, status colors and four state patterns keep their geometry and semantics. The updated consumer rejects legacy 1.0, cropped or uniformly occluded second rows and inconsistent two-row capacity.

`tools/smoke_ticket16_layout_app.py --output <isolated-evidence-directory>` produces actual Tk/Quartz monitoring and completed captures through configured sample-json sources, non-identity mapping and disk audit reconstruction. The separate upper repo `tools/verify_ticket16_layout_frames.py` reads these pixels through its frame gate and fake action outlet. `tools/smoke_state_marker_app.py` supplies new 1.1 conflict/alarm/complete/new-round captures for the upper frame replay. Original Ticket 12 1.0 samples remain historical evidence and are not claimed as current-version acceptance.
