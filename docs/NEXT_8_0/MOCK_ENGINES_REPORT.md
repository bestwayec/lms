# GRANDEC NEXT 8.0 — Full Mock Engines Report

## Blueprints Implemented (`apps/tests/blueprints.py`)
Exposed via `GET /api/tests/english/blueprints/`:
1. **`IELTS_ACADEMIC_V1` (`ielts_academic`)**:
   - `LISTENING` (30 min, 4 parts, 40Q, `IELTS_LISTENING_40`)
   - `READING` (60 min, 3 parts, 40Q, `IELTS_ACADEMIC_READING_40`)
   - `WRITING` (60 min, 2 tasks: Task 1 Academic visual + Task 2 Essay)
   - `SPEAKING` (14 min, 3 parts)
2. **`IELTS_GENERAL_V1` (`ielts_general`)**:
   - Uses `IELTS_GENERAL_READING_40` (strict General Training curve: e.g. `30/40 = Band 6.0` vs Academic `30/40 = Band 7.0`).
3. **`UZBMB_MULTILEVEL_EN_2026_V2` (`cefr_multilevel`)**:
   - `LISTENING` (45 min, 6 parts, 35Q -> `0–75` anchor table)
   - `READING` (60 min, 5 parts, 35Q -> `0–75` anchor table)
   - `WRITING` (60 min, 3 tasks weighted `5/5/6 = 16` raw -> nonlinear BMB `UZBMB_MULTILEVEL_WRITING_16_TO_75` lookup)
   - `SPEAKING` (30 min, 4 parts weighted `5/5/5/6 = 21` raw -> nonlinear BMB `UZBMB_MULTILEVEL_SPEAKING_21_TO_75` lookup)
   - Thresholds: `B1` (`38–50`), `B2` (`51–64`), `C1` (`65–75`).

## Pending Overall & Word-Limit Safeguards
- **Never Premature Overall Scores**: When a Full Mock (`ielts_academic`, `ielts_general`, or `cefr_multilevel`) has `WRITING` or `SPEAKING` items in `pending` state, `submit_attempt` sets `TestAttempt.status = PENDING_GRADING`, keeps `band_score = None` (`IELTS`) or `overall = None` (`Multilevel`), and returns honest `is_estimate: True` scorecard payloads (`/api/tests/attempts/<id>/certificate-card/`).
- **Word Limit Rules**: `respects_word_limit_rule()` enforces `ONE_WORD` and `ONE_WORD_AND_OR_NUMBER` rules on `TEXT_MATCH` / `GAP_FILL` answers when configured on `Question.config["word_limit_rule"]`.
