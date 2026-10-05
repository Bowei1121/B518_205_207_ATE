# KVM display contract 1.0

This contract describes the Tk app's machine-readable top band. It is a local display contract for Ticket 12; Ticket 16 still owns upper-computer capture, deployment, pause/control behavior, and shared acceptance.

## Coordinate spaces and geometry

All coordinates below are Tk widget coordinate units relative to the `KVM RESULT` frame. They are logical app coordinates, not guaranteed physical display pixels. The frame is laid out in a 376-unit-wide, fixed-width app. A capture system must measure its own physical-pixel-to-Tk-unit scale; it must not assume Retina scale, `tk scaling`, or an arbitrary remote-desktop resize factor. The app's tests use Tk scaling 1.0 and 1.5, but this does not establish remote KVM compatibility.

| Element | Tk geometry | Purpose |
| --- | --- | --- |
| Left locator | origin `(82, 2)`, 22×22; white 8×8 inset at `(3, 3)` | Asymmetric orientation/scale anchor |
| State marker | origin `(278, 0)`, 26×26 | 2×2 state pattern, no text required |
| Right locator | origin `(320, 2)`, 22×22; white 8×8 inset at `(11, 11)` | Opposite asymmetric orientation/scale anchor |
| Result cell | 34×26, 27-unit row step; first row begins at y=34 | Fixed ten-column product result band |

The state marker uses a white background and a 2-unit quiet zone. Each black/white cell is 10×10, with a 2-unit horizontal and vertical gap. The locator, state marker, and product band occupy separate regions. For capacity 1–10, the result band is one row of ten cells; for 11–20 it is two rows of ten, with positions 1–10 above 11–20. Capacity-external cells remain black. The marker is above the band and does not use its black cells.

## State patterns

Rows are top-to-bottom and columns left-to-right. `B` is `#000000`, `W` is `#ffffff`. The locators establish orientation; OCR is not part of state recognition.

| State | Top row | Bottom row | Snapshot meaning |
| --- | --- | --- | --- |
| Standby | `B W` | `W B` | No released current round, including not started, start failure, or manual stop |
| Monitoring | `B B` | `W W` | Round is running/preparing with no required confirmation |
| Review | `B W` | `B W` | Conflict or unacknowledged round alarm; collection may continue or be stopped |
| Complete | `W B` | `B W` | Snapshot says COMPLETED and results are available |

Mapping precedence is complete only when both the public snapshot state is `COMPLETED` and `result_available` is true; then any conflict, alarm, or awaiting-review state maps to Review; a running round maps to Monitoring; all other states map to Standby. Closing a review window does not change the snapshot. The Tk renderer obtains one `RoundSnapshot` and updates result cells and marker during the same UI callback. It redraws the marker only when the state changes to avoid flashing.

## Sampling and rejection limits

For each of the four cells, sample a center-area grayscale average after locating and orienting the marker. Values `0–80` classify as black and `176–255` as white. Values `81–175`, missing cells, out-of-range values, or a four-bit pattern outside this contract produce **unknown**, never Complete. This is a minimum input-quality gate, not a validated remote-image recognizer. Sampling crop size, compression, perspective, occlusion, and inter-frame consistency must be verified by the consumer.

The automated classifier tests exact patterns and rejects low-contrast, missing, and unknown samples. Tk tests cover scale settings 1.0 and 1.5 and ensure the marker stays above the result band while twenty detail rows scroll. Actual KVM hardware, capture dimensions, transport/compression, remote scaling, and upper-computer recognition were unavailable during this ticket; no support claim is made for those conditions. Ticket 16 must measure the deployed capture path and repeat the sample recognition against that system.

## Reproducible artifacts

Ticket 12's controlled Tk screenshots and run metadata are stored under `evidence/ticket-12/`. They contain synthetic/anonymized values only and are not actual KVM captures. `tools/smoke_state_marker_app.py` recreates the four states through the app's shared round interface and captures the app window on macOS.
