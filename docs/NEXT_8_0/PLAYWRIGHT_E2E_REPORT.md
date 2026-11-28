# GRANDEC NEXT 8.0 — Chromium Playwright E2E Verification Report

## Environment
- **Backend**: Live Django (`config.settings.e2e`, SQLite migrated cleanly across all 21 Django apps, seeded with Student, Teacher, Admin, 3 Full 4-Skill Mock Exams, Speaking Topic, Vocabulary Mistakes, and 10 Grammar Categories).
- **Frontend**: Live Vite dev server (`http://127.0.0.1:5173` -> `http://127.0.0.1:8000`).
- **Browser**: Headless Chromium via Python Playwright (`sync_playwright`, launched with `--use-fake-device-for-media-stream`, `--use-fake-ui-for-media-stream`, and `--use-file-for-fake-audio-capture`).

## End-to-End Full Mock Journeys Executed (`task-8528`)
All roles authenticated via real `/login` SPA form (`POST /api/auth/login/` -> `200 OK`):

1. **IELTS Academic Full Mock (`ielts_academic`)**:
   - Listening (`TEXT_MATCH`), Reading (`SINGLE_CHOICE` with Passage), Writing (`WRITTEN`), Speaking (`SPEAKING_PROMPT` real Chromium WebM/Opus fake-mic upload -> `/api/tests/attempts/<id>/questions/<qid>/speaking/`).
   - Submit -> inline `.cefr-result-page` (`pending_grading`), Logout -> `leftover_draft_keys: []`.
   - Teacher Workspace Writing + Speaking reviews -> Auto-finalize -> Gradebook (`grading_status: "graded"`) -> Student Certificate Card (`overall_band`, `grading_status: "graded"`).
2. **IELTS General Training Full Mock (`ielts_general`)**:
   - Full 4-skill flow + Speaking WebM/Opus capture + Teacher review + Gradebook & Certificate Card parity (`grading_status: "graded"`).
3. **CEFR Multilevel Full Mock (`cefr_multilevel`)**:
   - Full 4-skill flow + Speaking WebM/Opus capture -> Writing `13/16 -> 63 (B2)`, Speaking `58/75 (B2)`, Listening `75 (C1)`, Reading `75 (C1)` -> Overall `67.8 (C1)`, `grading_status: "graded"`, `has_certificate: true`.

## Additional Studios & Auth Checks Verified Live
- **Writing Studio (`/essays/studio`)**: Essay saved to backend draft (`POST /api/v1/essays/ielts/draft/`), reloaded cleanly, and verified preserved in `section textarea`.
- **Speaking Practice (`/speaking/practice/<id>`)**: Microphone readiness & timer flow rendered cleanly (`speaking_practice_1366.png`).
- **Vocabulary Studio (`/vocabulary`) & Grammar Studio (`/grammar`)**: Word deck and seeded Grammar topics rendered cleanly.

## Responsive Viewport & Theme Matrix (`360px`..`1920px`, `task-8528`)
| Width (px) | Horizontal Overflow (`/english`, `/essays/studio`, `/vocabulary`, `/grammar`) | Light & Dark / Theme Checks |
| :--- | :--- | :--- |
| `360` | `false` (`overflows: []`) | `/english` `360px` search input (`paddingLeft: 38`, `clearGap: 12px` from search icon) |
| `390` | `false` (`overflows: []`) | `/tma` Mobile shell clean (`tma_390_dark.png`) |
| `768` | `false` (`overflows: []`) | Clean reflow |
| `1024` | `false` (`overflows: []`) | Clean reflow |
| `1366` | `false` (`overflows: []`) | Admin `/panel` Dark Mode (`cardBg: rgb(22, 32, 51)`, `cardColor: rgb(248, 250, 252)`), English Dark buttons fixed (`english_1366_dark.png`) |
| `1920` | `false` (`overflows: []`) | Clean desktop layout |

## Runtime Error Telemetry (`task-8528`)
- **Browser `console.error` count**: `0`
- **Uncaught `pageerror` exceptions**: `0`
- **HTTP `5xx` server responses**: `0`
