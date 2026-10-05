# Ticket 14 controlled sample format

These fixtures are anonymous architecture samples. They do not represent a real
ATE platform, supported hardware capacity, production configuration, or KVM feed.

Copy one fixture into an isolated source directory as `events.jsonl` after the
monitor starts. The monitor snapshots existing file lengths during preparation,
so startup history is ignored. Each complete UTF-8 JSON object occupies one line;
the newline marks the record complete. A partial final line remains unread until
its newline arrives.

The accepted schema is `sample-json/v1`:

- `kind`: `activity` or `final`.
- `position`: source position from 1 through 20.
- `sn`: optional string; omitted or empty means unknown.
- `source_time`: optional platform-provided timestamp string; omitted means unknown.
- `batch_id`: optional explicit sample batch identity. When present, its value and
  source position form comparable same-round evidence. It is not inferred from
  the App round ID, file name, directory or copy time.
- `status`: required for `final`, one of `PASS`, `FAIL`, or `NOTEST`.

Invalid JSON, invalid fields and unsupported final states do not become results.
Positions that are valid for the format but not in the selected profile mapping
are reported as unmapped source evidence. They do not change a displayed result.

`activity.jsonl` contains one active observation and two final results, including
a final-only position. `conflict.jsonl` adds a contradictory result for position
20 with explicit matching batch evidence. `final-only.jsonl` contains final
results without activity; it intentionally proves that the Adapter does not
invent TESTING or a test start time.
