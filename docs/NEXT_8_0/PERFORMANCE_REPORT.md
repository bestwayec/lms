# GRANDEC NEXT 8.0 — Performance, Bundle & Migration Benchmarks

## 1. Vite Production Bundle Comparison (`origin/main @ 5db1a43` vs `NEXT 8.0`)
Measured directly via isolated `git worktree` build on `origin/main` vs final `NEXT 8.0` `dist/` (`tsc -b && vite build`):

| Metric | `origin/main` (`v2.12.0`) | `NEXT 8.0` (Final) | Delta |
| :--- | :--- | :--- | :--- |
| JS Chunks | `124` | `127` | `+3` lazy routes |
| Total JS (raw / gzip) | `2876.78 kB` / `838.55 kB` | `2956.77 kB` / `860.30 kB` | `+21.75 kB` gzip (`+2.6%`) |
| Total CSS (raw / gzip) | `247.10 kB` / `43.57 kB` | `262.02 kB` / `45.33 kB` | `+1.76 kB` gzip |
| **Initial Entry Transfer (`index.html` script/CSS)** | **`961.10 kB` / `266.53 kB` gzip** | **`984.43 kB` / `270.90 kB` gzip** | **`+4.37 kB` gzip (`+1.6%`)** |
| Latest Clean Build Time (`task-8514`) | `44.92s` (cold worktree) | **`2.62s`** (warm workspace) | `0` TS errors, `0` warnings |

## 2. Backend SQL Query Count Parity (PostgreSQL 17.11)
Measured via Django `CaptureQueriesContext` across 15 seeded tests + historical attempts/results/essays against real PostgreSQL 17.11 (`lms_pg_mig_audit`):

| Endpoint | `origin/main` Queries (ms) | `NEXT 8.0` Queries (ms) | Regression? |
| :--- | :--- | :--- | :--- |
| `GET /api/tests/` (`200 OK`) | `11` (`62.92 ms`) | `11` (`55.65 ms`) | None (`0` extra queries) |
| `GET /api/tests/?subject=uzbek` (`200 OK`) | `11` (`69.33 ms`) | `11` (`62.25 ms`) | None (`0` extra queries) |
| `GET /api/tests/<id>/` (`200 OK`) | `16` (`73.89 ms`) | `16` (`73.89 ms`) | None (`0` extra queries) |

## 3. PostgreSQL 17.11 Migration & Rollback Compatibility (`v2.12.0` -> `NEXT 8.0`)
- **Forward migration**: Seeded real `v2.12.0` PostgreSQL 17.11 DB (`origin/main`) with legacy Uzbek users, tests, completed attempts, results, and essays, then migrated forward to `NEXT 8.0` (`accounts.0027`, `essays.0024`, `speaking.0002`, `tests.0025`, `tests.0026`, `vocabulary.0002`) in **`15.41s`** with `data_preserved: true` and `200 OK` on legacy endpoints.
- **Reverse migration**: Executed `manage.py migrate <app> <v2.12.0_target>` across all 5 apps (`accounts`, `vocabulary`, `speaking`, `essays`, `tests`) -> exit code `0` on all 5 apps, then re-applied forward (`reapply_rc: 0`). Standard `DEPLOYMENT_GUIDE.md` release rollback relies on pre-deploy DB snapshot restore + image pin (`sha-xxxxxxx`).
