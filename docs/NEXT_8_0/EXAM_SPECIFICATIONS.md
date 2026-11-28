# GRANDEC NEXT 8.0 — Exam Specifications & Scoring Rules

**Spec Checked On:** `2026-11-27` (`apps/tests/blueprints.py`, `SPEC_CHECKED_ON = "2026-11-27"`, `is_official: False`)

## Official & Reference Sources
- `ielts-format`: https://ielts.org/take-a-test/test-types/ielts-academic-test
- `ielts-scoring`: https://ielts.org/take-a-test/your-results/ielts-scoring-in-detail
- `idp-computer-delivered`: https://ielts.idp.com/canada/prepare/article-how-computer-delivered-ielts-works
- `uzbmb-format`: https://uzbmb.uz/page/test_sinovlari_formati
- `uzbmb-criteria-2023`: https://uzbmb.uz/upload/file/pdf/Multilevel-bm.pdf
- `uzbmb-writing-2025`: https://api-portal.gov.uz/uploads/165/2025/10/13/99dfbb36-0f1d-2c70-8a4e-e1382a5f255b_media_.pdf
- `uzbmb-speaking-format`: https://uzbmb.uz/upload/file/pdf/phone/Speaking_format.pdf
- `uzbmb-speaking-criteria`: https://uzbmb.uz/upload/file/pdf/phone/yangi_format_eng.pdf
- Reference architecture & lookup parity: `bestwayec/bestway @ 67b92f5419e0bf9e95f2a16852019aef3c72659e` (strictly read-only)

## 1. IELTS Academic (`IELTS_ACADEMIC_V1` / `ielts_academic`, Practice Estimate)
- **Listening**: ~30 min (`duration_approximate: True`, `audio_plays: 1`, CD preview/2-min review window), 4 parts, 40 questions -> `IELTS_LISTENING_40` raw-to-band table (`39+=9.0`, `37+=8.5`, `35+=8.0`, `32+=7.5`, `30+=7.0`, `26+=6.5`, `23+=6.0`, `18+=5.5`, `16+=5.0`, ...).
- **Reading**: 60 min (`duration_approximate: False`), 3 passages (`stimulusRef`-isolated), 40 questions -> `IELTS_ACADEMIC_READING_40` (`39+=9.0`, `37+=8.5`, `35+=8.0`, `33+=7.5`, `30+=7.0`, `27+=6.5`, `23+=6.0`, `19+=5.5`, `15+=5.0`, `10+=4.0`, ...).
- **Writing**: 60 min, Task 1 (Academic chart/process, min 150 words) + Task 2 (Essay, min 250 words) -> 4 IELTS criteria (`0.0–9.0` step `0.5`). Official Task 2 `2x` weighting enforced in `_writing_band_from_items`: `round_half((Task1 + 2 * Task2) / 3)`.
- **Speaking**: 11–14 min (`duration_approximate: True`), Parts 1, 2, 3 -> 4 criteria (`FC`, `LR`, `GRA`, nullable acoustic `PR`).
- **Overall Band**: Cambridge half-band rounding over `(L + R + W + S) / 4`; held strictly as `None` (`pending_grading`) whenever Writing or Speaking is ungraded.

## 2. IELTS General Training (`IELTS_GENERAL_V1` / `ielts_general`, Practice Estimate)
- Identical Listening (`audio_plays: 1`), Writing (`Task 2 = 2x Task 1`), Speaking, and overall rounding rules, with Task 1 General Letter prompts and the dedicated `IELTS_GENERAL_READING_40` conversion curve (`40=9.0`, `39=8.5`, `37+=8.0`, `36=7.5`, `34+=7.0`, `32+=6.5`, `30+=6.0`, `27+=5.5`, `23+=5.0`, `19+=4.5`, `15+=4.0`, `10+=3.0`).

## 3. CEFR Multi-level (`UZBMB_MULTILEVEL_EN_2026_V2` / `cefr_multilevel`, Practice Estimate)
- **Scale**: `0–75` estimated practice scale (`is_estimate: True`, `is_official: False`; IELTS bands strictly excluded).
- **Listening**: 45 min (`audio_plays: 2` per UZBMB format), 6 parts, 35 questions (`cefr_multilevel.raw_to_scaled`).
- **Reading**: 60 min, 5 parts, 35 questions (`cefr_multilevel.raw_to_scaled`).
- **Writing**: 60 min, Tasks `1.1` (max 5) + `1.2` (max 5) + `2` (max 6) = `16` raw -> nonlinear lookup `UZBMB_MULTILEVEL_WRITING_16_TO_75`.
- **Speaking**: `30 min` generous mock session cap (`duration_approximate: True`, disclosed in blueprint notes alongside official ~15 min live pace with per-part prep/response timings `1.1`, `1.2`, `2`, `3`), Parts `1.1` (5), `1.2` (5), `2` (5), `3` (6) = `21` raw -> nonlinear lookup `UZBMB_MULTILEVEL_SPEAKING_21_TO_75`.
- **Certification Thresholds**: `B1` (`38–50`), `B2` (`51–64`), `C1` (`65–75`), `BELOW_B1` (`<38`). Overall level reported only when all 4 sections are scored.

## 4. Word Limit Normalization
- `respects_word_limit_rule()` enforces `ONE_WORD` (single lexical word) and `ONE_WORD_AND_OR_NUMBER` (`<= 1` word + `<= 1` number token) across `TEXT_MATCH` and `GAP_FILL` questions when `Question.config["word_limit_rule"]` is configured.
