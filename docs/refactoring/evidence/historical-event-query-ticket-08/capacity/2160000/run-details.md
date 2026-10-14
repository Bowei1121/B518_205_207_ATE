# Capacity run details — 2160000

Fixture: 2,160,000 synthetic saved events, 2,151 logical sources / 2,152 physical source files, 881,916,094 bytes; {'app_journal': 10800, 'legacy_events_log': 108000, 'round_audit': 2041200}; query 2026-07-17–2026-10-14 inclusive local dates (+08:00).

Each table preserves all three runs. `query s` is query duration; `verify s` is additional identity verification; `parse/reuse` counts logical source files; `reader bytes` are bytes consumed by parser, not physical device I/O; RSS is process peak RSS; `snapshot/index` are on-disk query snapshot and persistent index; page scenario includes first/middle/last page latencies in the raw report. Workers after cleanup are retained per raw JSON. Initial/reuse/change/degradation digests cover the full result set. The page scenario digest covers only its selected first/middle/last pages and the exact sampled-row count below.

## First index build

| Run | Query s | Verify s | Parsed / reused | Reader bytes | Peak RSS MiB | Snapshot MiB | Index MiB | Count | Page size | Cleanup workers | Identity / notes |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 1283.654 | 1024.759 | 2151 / 0 | 1,747,718,548 | 200.2 | 3330.8 | 5128.2 | 1,620,000 | 100 | 0 | full identity SHA e83b7030adce36a0 |
| 2 | 1681.299 | 1155.973 | 2151 / 0 | 1,747,718,548 | 147.3 | 3330.8 | 5128.2 | 1,620,000 | 100 | 0 | full identity SHA e83b7030adce36a0 |
| 3 | 1424.041 | 927.307 | 2151 / 0 | 1,747,718,548 | 183.9 | 3330.8 | 5128.2 | 1,620,000 | 100 | 0 | full identity SHA e83b7030adce36a0 |

## Fresh-process valid-index reuse

| Run | Query s | Verify s | Parsed / reused | Reader bytes | Peak RSS MiB | Snapshot MiB | Index MiB | Count | Page size | Cleanup workers | Identity / notes |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 480.465 | 892.501 | 0 / 2151 | 0 | 199.2 | 3330.8 | 5128.2 | 1,620,000 | 100 | 0 | full identity SHA e83b7030adce36a0 |
| 2 | 744.463 | 996.962 | 0 / 2151 | 0 | 149.1 | 3330.8 | 5128.2 | 1,620,000 | 100 | 0 | full identity SHA e83b7030adce36a0 |
| 3 | 485.302 | 1006.899 | 0 / 2151 | 0 | 149.8 | 3330.8 | 5128.2 | 1,620,000 | 100 | 0 | full identity SHA e83b7030adce36a0 |

## Single-source change

| Run | Query s | Verify s | Parsed / reused | Reader bytes | Peak RSS MiB | Snapshot MiB | Index MiB | Count | Page size | Cleanup workers | Identity / notes |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 476.969 | 996.619 | 1 / 2150 | 838,307 | 149.7 | 3330.8 | 5128.2 | 1,620,001 | 100 | 0 | full identity SHA e5ebea14ba497f34 |
| 2 | 463.108 | 987.351 | 1 / 2150 | 838,307 | 157.6 | 3330.8 | 5128.2 | 1,620,001 | 100 | 0 | full identity SHA e5ebea14ba497f34 |
| 3 | 496.687 | 988.163 | 1 / 2150 | 838,307 | 149.2 | 3330.8 | 5128.2 | 1,620,001 | 100 | 0 | full identity SHA e5ebea14ba497f34 |

## Index degradation / rebuild

| Run | Query s | Verify s | Parsed / reused | Reader bytes | Peak RSS MiB | Snapshot MiB | Index MiB | Count | Page size | Cleanup workers | Identity / notes |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 1439.328 | 1076.174 | 2151 / 0 | 1,747,718,548 | 177.3 | 3330.8 | 5128.2 | 1,620,000 | 100 | 0 | full identity SHA e83b7030adce36a0; The historical query index was rebuilt. |
| 2 | 1217.475 | 882.790 | 2151 / 0 | 1,747,718,548 | 168.2 | 3330.8 | 5128.2 | 1,620,000 | 100 | 0 | full identity SHA e83b7030adce36a0; The historical query index was rebuilt. |
| 3 | 1209.379 | 875.676 | 2151 / 0 | 1,747,718,548 | 156.7 | 3330.8 | 5128.2 | 1,620,000 | 100 | 0 | full identity SHA e83b7030adce36a0; The historical query index was rebuilt. |

## Page navigation

| Run | Query s | Verify s | Parsed / reused | Reader bytes | Peak RSS MiB | Snapshot MiB | Index MiB | Count | Page size | Cleanup workers | Identity / notes |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 346.823 | 0.168 | 0 / 2151 | 0 | 149.0 | 3330.8 | 5128.2 | 1,620,000 | 100 | 0 | anchor-page SHA (300 sampled rows) 86f32e93395bca67; page latencies [{"page_number":1,"seconds":0.00413082300002543},{"page_number":8100,"seconds":0.05214974500000835},{"page_number":16200,"seconds":0.10062016099999482}] |
| 2 | 323.048 | 0.159 | 0 / 2151 | 0 | 220.1 | 3330.8 | 5128.2 | 1,620,000 | 100 | 0 | anchor-page SHA (300 sampled rows) 86f32e93395bca67; page latencies [{"page_number":1,"seconds":0.004246109000007436},{"page_number":8100,"seconds":0.04852847000000793},{"page_number":16200,"seconds":0.09215035200003285}] |
| 3 | 323.313 | 0.169 | 0 / 2151 | 0 | 157.6 | 3330.8 | 5128.2 | 1,620,000 | 100 | 0 | anchor-page SHA (300 sampled rows) 86f32e93395bca67; page latencies [{"page_number":1,"seconds":0.004935482999997021},{"page_number":8100,"seconds":0.0513297129999728},{"page_number":16200,"seconds":0.09622170200003666}] |

Independent raw-file baseline: 1,620,000 in-range events; complete identity SHA-256 `e83b7030adce36a019e90ea49af55403a1e1b703c42b480878d4116929ff77a3`. All listed scenarios returned exit code 0. OS disk cache controlled: `False`. Source bytes preserved after benchmark: `True`.
