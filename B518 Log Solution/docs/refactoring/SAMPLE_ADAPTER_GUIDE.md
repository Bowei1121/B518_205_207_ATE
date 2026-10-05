# Controlled sample Adapter

Ticket 14 registers `sample-json` as an in-process architecture fixture. It is
available in the engineer profile editor for the `SAMPLE` project and `FCT`
machine. Operators continue to select project and machine; there is no separate
platform picker in the main monitoring workflow.

The common platform registry describes each format's supported machine types,
source positions, required and optional paths, path labels, and monitor factory.
Profile validation and App source preparation use those same capabilities. The
Tk layer passes a generic profile and source context to the registry; it does not
select a monitor with format-specific UI or lifecycle branches.

The sample format consumes complete UTF-8 JSON Lines records appended to
`events.jsonl`. The exact fields, examples, batch evidence, unknown values,
startup snapshot behavior, and invalid record handling are documented in
[`testdata/ticket-14/README.md`](../../B518%20Log%20Solution/testdata/ticket-14/README.md).
Valid source positions are 1–20. That is a parser fixture limit only; it does
not represent supported instrument or fixture capacity. A profile still limits
effective positions and maps source positions independently to display
positions. An observed source outside the profile mapping remains an
`unmapped_source` event and does not produce or replace a channel result.

The Adapter turns observed `activity` into TESTING and passes final PASS, FAIL,
or NOTEST evidence to the existing `ConfiguredMonitor` and `RoundCoordinator`
interfaces. Invalid JSON, fields or final statuses emit warning evidence rather
than results. It does not create clocks, timeout policies, conflict review,
alarms, stop/release behavior, KVM markers, or audit policy. The shared round
snapshot, candidate queue, operator actions and audit journal remain the source
of truth. A missing source time is recorded as unknown; a missing `batch_id`
does not receive an inferred same-round identity.

To replay the fixtures, create an isolated `SAMPLE` / `FCT` profile from
`testdata/ticket-14/sample-profile.json`, replace the path with a writable
temporary source directory, select the configuration in the ordinary project
and machine selectors, and start the Tk App. Copy one fixture to that directory
as `events.jsonl` after the monitor has started. For a conflict, use
`conflict.jsonl`; select the captured conflict in the existing non-modal review
window and invoke either existing result choice. The alarm and conflict remain
independent blockers. Use the existing Session view and
`tools/rebuild_round_audit.py` to inspect the persisted round events.

Adding another production format still requires a code change and a new App
build. This registration API is not a dynamic plugin loader. These samples
prove the adapter boundary and the existing shared lifecycle only; they do not
claim support for a new device, actual KVM, target machine, published App, or
unknown same-round source adoption policy.
