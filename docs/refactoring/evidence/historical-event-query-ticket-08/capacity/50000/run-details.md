# Capacity run details — 50000

Fixture: 50,000 synthetic saved events, 52 logical sources / 53 physical source files, 20,328,118 bytes; {'app_journal': 250, 'legacy_events_log': 2500, 'round_audit': 47250}; query 2026-07-17–2026-10-14 inclusive local dates (+08:00).

Each table preserves all three runs. `query s` is query duration; `verify s` is additional identity verification; `parse/reuse` counts logical source files; `reader bytes` are bytes consumed by parser, not physical device I/O; RSS is process peak RSS; `snapshot/index` are on-disk query snapshot and persistent index; page scenario includes first/middle/last page latencies in the raw report. Workers after cleanup are retained per raw JSON. Initial/reuse/change/degradation digests cover the full result set. The page scenario digest covers only its selected first/middle/last pages and the exact sampled-row count below.

## First index build

| Run | Query s | Verify s | Parsed / reused | Reader bytes | Peak RSS MiB | Snapshot MiB | Index MiB | Count | Page size | Cleanup workers | Identity / notes |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 19.445 | 2.129 | 52 / 0 | 40,287,592 | 41.0 | 78.4 | 118.1 | 37,520 | 100 | 0 | full identity SHA 7e493f80ebed6a42 |
| 2 | 18.998 | 2.255 | 52 / 0 | 40,287,592 | 45.2 | 78.4 | 118.1 | 37,520 | 100 | 0 | full identity SHA 7e493f80ebed6a42 |
| 3 | 18.993 | 2.142 | 52 / 0 | 40,287,592 | 40.6 | 78.4 | 118.1 | 37,520 | 100 | 0 | full identity SHA 7e493f80ebed6a42 |

## Fresh-process valid-index reuse

| Run | Query s | Verify s | Parsed / reused | Reader bytes | Peak RSS MiB | Snapshot MiB | Index MiB | Count | Page size | Cleanup workers | Identity / notes |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 3.051 | 2.291 | 0 / 52 | 0 | 39.8 | 78.4 | 118.1 | 37,520 | 100 | 0 | full identity SHA 7e493f80ebed6a42 |
| 2 | 3.030 | 2.142 | 0 / 52 | 0 | 43.2 | 78.4 | 118.1 | 37,520 | 100 | 0 | full identity SHA 7e493f80ebed6a42 |
| 3 | 2.974 | 2.272 | 0 / 52 | 0 | 44.0 | 78.4 | 118.1 | 37,520 | 100 | 0 | full identity SHA 7e493f80ebed6a42 |

## Single-source change

| Run | Query s | Verify s | Parsed / reused | Reader bytes | Peak RSS MiB | Snapshot MiB | Index MiB | Count | Page size | Cleanup workers | Identity / notes |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 3.444 | 2.217 | 1 / 51 | 838,307 | 43.7 | 78.4 | 118.1 | 37,521 | 100 | 0 | full identity SHA 7e0cd449dcf7078f |
| 2 | 3.675 | 2.173 | 1 / 51 | 838,307 | 42.3 | 78.4 | 118.1 | 37,521 | 100 | 0 | full identity SHA 7e0cd449dcf7078f |
| 3 | 3.396 | 2.185 | 1 / 51 | 838,307 | 43.0 | 78.4 | 118.1 | 37,521 | 100 | 0 | full identity SHA 7e0cd449dcf7078f |

## Index degradation / rebuild

| Run | Query s | Verify s | Parsed / reused | Reader bytes | Peak RSS MiB | Snapshot MiB | Index MiB | Count | Page size | Cleanup workers | Identity / notes |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 21.740 | 2.126 | 52 / 0 | 40,287,592 | 41.8 | 78.4 | 118.1 | 37,520 | 100 | 0 | full identity SHA 7e493f80ebed6a42; The historical query index was rebuilt. |
| 2 | 25.029 | 2.180 | 52 / 0 | 40,287,592 | 41.6 | 78.4 | 118.1 | 37,520 | 100 | 0 | full identity SHA 7e493f80ebed6a42; The historical query index was rebuilt. |
| 3 | 24.998 | 2.181 | 52 / 0 | 40,287,592 | 42.7 | 78.4 | 118.1 | 37,520 | 100 | 0 | full identity SHA 7e493f80ebed6a42; The historical query index was rebuilt. |

## Page navigation

| Run | Query s | Verify s | Parsed / reused | Reader bytes | Peak RSS MiB | Snapshot MiB | Index MiB | Count | Page size | Cleanup workers | Identity / notes |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 6.282 | 0.017 | 0 / 52 | 0 | 38.4 | 78.4 | 118.1 | 37,520 | 100 | 0 | anchor-page SHA (220 sampled rows) b96fa2defe60281f; page latencies [{"page_number":1,"seconds":0.004511605000000252},{"page_number":188,"seconds":0.006026972999999991},{"page_number":376,"seconds":0.004583944000000173}] |
| 2 | 4.826 | 0.015 | 0 / 52 | 0 | 36.6 | 78.4 | 118.1 | 37,520 | 100 | 0 | anchor-page SHA (220 sampled rows) b96fa2defe60281f; page latencies [{"page_number":1,"seconds":0.004219138000000733},{"page_number":188,"seconds":0.005364886999999818},{"page_number":376,"seconds":0.003783803000000141}] |
| 3 | 2.968 | 0.016 | 0 / 52 | 0 | 37.4 | 78.4 | 118.1 | 37,520 | 100 | 0 | anchor-page SHA (220 sampled rows) b96fa2defe60281f; page latencies [{"page_number":1,"seconds":0.004177422000000153},{"page_number":188,"seconds":0.006143079000000107},{"page_number":376,"seconds":0.003735398000000334}] |

Independent raw-file baseline: 37,520 in-range events; complete identity SHA-256 `7e493f80ebed6a42860f38653537ba3f0c9a6264c71e864776c02102487b3ff7`. All listed scenarios returned exit code 0. OS disk cache controlled: `False`. Source bytes preserved after benchmark: `True`.
