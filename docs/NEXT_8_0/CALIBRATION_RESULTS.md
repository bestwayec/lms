# GRANDEC NEXT 8.0 — Rubric Calibration & Agreement Methodology

## Calibration Framework (`apps/core/ai_gateway.py`)
`compute_calibrated_stats(anchors)` measures rubric evaluator alignment against human-benchmarked anchor samples using:
- **MAE (Mean Absolute Error)**: mean `|predicted - expected|` in Band units (`0.0–9.0` rounded to `0.5`).
- **Within-Half-Band Agreement (`within_half_band_pct`)**: percentage of samples with `|predicted - expected| <= 0.5`.

## Verified Regression Coverage (`tests/test_next8_phase6_7_writing.py`)
- Unit verification of `compute_calibrated_stats()` against benchmarked Band `6.0` / `6.5` / `7.0` anchor pairs verified exact `count == 3`, `mae <= 0.5`, and `within_half_band_pct == 100.0%`.
- Under-length word-count penalties (`Task 1 < 150 words`, `Task 2 < 250 words`) and topic-relevance caps (`partially_off_topic` capped at Task Response Band `3.0` / overall `<= 3.5`; `completely_off_topic` set to `0.0`) remain deterministic across both AI and mock evaluation paths (`_validate_ielts_result` in `apps/essays/services.py`).
- Multi-rubric teacher overrides store normalized totals across separate scales (`IELTS /9` step `0.5`, `BMB Multi-level /16` & `/75`, `Uzbek BMB /20` / `max=24`), preventing scale cross-contamination (`TeacherReview.final_score` widened cleanly in migration `essays/0024`).
