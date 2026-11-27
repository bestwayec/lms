# GRANDEC NEXT 8.0 — Exam Specifications & Scoring Rules

## 1. IELTS Academic (`IELTS_ACADEMIC_V1` / `ielts_academic`)
- **Listening**: 30 min, 4 parts, 40 questions -> `IELTS_LISTENING_40` raw-to-band table (`39+=9.0`, `37+=8.5`, `35+=8.0`, `32+=7.5`, `30+=7.0`, `26+=6.5`, `23+=6.0`, `18+=5.5`, `16+=5.0`, ...).
- **Reading**: 60 min, 3 passages (`stimulusRef`-isolated), 40 questions -> `IELTS_ACADEMIC_READING_40` (`39+=9.0`, `37+=8.5`, `35+=8.0`, `33+=7.5`, `30+=7.0`, `27+=6.5`, `23+=6.0`, `19+=5.5`, `15+=5.0`, ...).
- **Writing**: 60 min, Task 1 (Academic chart/process, min 150 words) + Task 2 (Essay, min 250 words) -> 4 IELTS criteria (`0.0–9.0` step `0.5`).
- **Speaking**: 11–14 min, Parts 1, 2, 3 -> 4 criteria (`FC`, `LR`, `GRA`, nullable acoustic `PR`).
- **Overall Band**: Cambridge half-band rounding over `(L + R + W + S) / 4`; held strictly as `None` (`pending_grading`) whenever any Writing or Speaking section is ungraded.

## 2. IELTS General Training (`IELTS_GENERAL_V1` / `ielts_general`)
- Identical Listening, Writing Task 2, Speaking, and overall rounding rules, with Task 1 General Letter prompts and the dedicated `IELTS_GENERAL_READING_40` conversion curve (`40=9.0`, `39=8.5`, `37+=8.0`, `36=7.5`, `34+=7.0`, `32+=6.5`, `30+=6.0`, ...).

## 3. CEFR Multi-level (`UZBMB_MULTILEVEL_EN_2026_V2` / `cefr_multilevel`)
- **Scale**: `0–75` estimated practice scale (`is_estimate: True`; no IELTS band leaked into Multilevel scorecards).
- **Listening**: 45 min, 6 parts, 35 questions (`cefr_multilevel.raw_to_scaled`).
- **Reading**: 60 min, 5 parts, 35 questions (`cefr_multilevel.raw_to_scaled`).
- **Writing**: 60 min, Tasks `1.1` (max 5) + `1.2` (max 5) + `2` (max 6) = `16` raw -> nonlinear lookup `UZBMB_MULTILEVEL_WRITING_16_TO_75`.
- **Speaking**: 30 min, Parts `1.1` (5), `1.2` (5), `2` (5), `3` (6) = `21` raw -> nonlinear lookup `UZBMB_MULTILEVEL_SPEAKING_21_TO_75`.
- **Certification Thresholds**: `B1` (`38–50`), `B2` (`51–64`), `C1` (`65–75`), `BELOW_B1` (`<38`). Overall level reported only when all 4 sections are scored.

## 4. Word Limit Normalization
- `respects_word_limit_rule()` enforces `ONE_WORD` (single lexical word) and `ONE_WORD_AND_OR_NUMBER` (`<= 1` word + `<= 1` number token) across `TEXT_MATCH` and `GAP_FILL` questions when `Question.config["word_limit_rule"]` is configured.
