# R3 field acceptance checklist

Status: **Pending scheduling and execution with factory engineering.** This checklist is a handoff artifact. No equipment, operator, configuration, or result has been prefilled or inferred.

Complete one record per supported platform/configuration exercised. Attach logs, screenshots, or exported round evidence using the site's approved handling process; do not place production logs or sensitive serial numbers in this repository.

## Run record

| Field | To be completed on site |
| --- | --- |
| Site / line / station | |
| Equipment identifier | |
| Equipment / fixture version | |
| OS and version | |
| App version / commit | |
| Configuration identifier / revision | |
| Project and station type | |
| Platform and source format | |
| Source directories used | |
| Engineer / operator | |
| Date and local time zone | |
| Result: pass / fail / blocked | |
| Evidence location / ticket | |
| Notes and limitations | |

## Procedure

| # | Operation | Expected result | Actual result / evidence |
| --- | --- | --- | --- |
| 1 | Engineer selects the approved project and station configuration. | Correct platform, capacity, paths and position mapping are shown by the deployed App configuration. | |
| 2 | Confirm each required source directory is reachable; confirm configured optional sources follow their documented blank/optional behavior. | Start accepts only the intended, readable configuration. No blank path is treated as the current directory. | |
| 3 | Start with the normal button. | Existing prompt and busy-state behavior appears; a round is accepted and sources prepare in the background. | |
| 4 | Observe the platform's source records at the configured positions. | Capacity, position mapping, serial/result display, events, and source timestamps match the equipment output. | |
| 5 | Exercise the approved local shortcut. If the site's global shortcut setup is part of the acceptance plan, exercise it separately. | The request is handled on the Tk event loop and follows the documented start-entry behavior. Record OS-level shortcut acceptance separately. | |
| 6 | Repeat a start request while the round is RUNNING. | The current round and displayed results remain intact; no new round replaces it. | |
| 7 | Stop a round and, if safely available, exercise a controlled source-preparation failure or timeout. | The App reports the existing failure state, restores controls, retains the accepted round and its evidence, and does not restart collection when a late source becomes ready. | |
| 8 | Close after a successful round. If the approved test plan includes a save failure, restore the destination and retry. | The App remains responsive while saving, closes only after complete Session and audit persistence, and retains failure details until recovery succeeds. | |
| 9 | Reopen the saved record with the approved reader/tooling. | Session and audit agree on the frozen configuration, positions, results, and event order. | |

## Completion

| Field | To be completed on site |
| --- | --- |
| Overall decision | |
| Open issues / follow-up owner | |
| Factory engineer approval | |
| Approval date | |
| Evidence links or controlled storage references | |

This field exercise is separate from the R3 code and controlled-Tk delivery. Until the rows above contain actual equipment evidence and engineering approval, physical equipment acceptance remains pending.
