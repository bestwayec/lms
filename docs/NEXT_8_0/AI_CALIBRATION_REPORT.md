# GRANDEC NEXT 8.0 — AI Calibration, Cost & Honesty Limitations Report

## What Was Verified
1. **Honest Refusal & Quota Refund**:
   - Short writing (`<12` lexical English words, `MIN_WRITING_EVIDENCE_WORDS`) returns `400 code="rejected"`.
   - Missing/unavailable AI providers return `503 code="not_graded"` with automatic allowance refund (`enforce_essay_quota`/`release_usage` and `consume_feature_cap`/`refund_feature_cap`).
2. **Evidence Grounding (`apps/core/ai_gateway.py`)**:
   - Quoted snippets and `corrections` in AI criterion responses are matched against the exact submitted text to populate `start_offset`, `end_offset`, and `quote_verified`, including repeated-phrase disambiguation and curly-quote normalization. Unverified hallucinations receive `quote_verified = False`, `start_offset = -1` and are never rendered as fake inline highlights.
3. **Speaking Pronunciation & Incomplete-Band Honesty (`apps/speaking/services.py`)**:
   - Transcript-only evaluations store `pronunciation_score = None` (`not_measured_from_transcript`) and leave `overall_band = None` / `final_score = None` (`feedback["is_partial_estimate"] = True`) until full acoustic or Teacher finalization occurs; UI removes misleading `"Rasmiy baholash"` labels.
   - Audio uploads undergo local WAV (`wave`) and browser WebM/OGG/Opus (`av>=14.0,<20.0`, PyAV `19.0.2` verified locally + Chromium E2E) container integrity and bounded duration checks (`apps/speaking/audio_verify.py`).
4. **Calibration Utility**:
   - `compute_calibrated_stats()` verifies MAE and within-0.5-band accuracy on anchor pairs (`tests/test_next8_phase6_7_writing.py`).

## Explicit Limitations (Disclosed Honestly)
- Live external LLM calls (OpenRouter / Gemini multimodal fallback) were **not** executed against paid external API keys during automated CI/local test runs; automated test coverage exercises mocked provider contracts + explicit fault/unavailable/calibration paths + `ESSAY_AI_MOCK_MODE=True` where explicitly configured.
- Live production AI examiner agreement (`MAE` against real certified IELTS/BMB human raters across live cohorts) remains `UNVERIFIED` pre-launch and must be evaluated post-deployment via `TeacherReview` vs AI score telemetry and `/api/v1/panel/ai-metrics/`.
- Linux container PyAV WebM/Opus decoding in CI/production Docker builds must be confirmed on Ubuntu CI runners (Docker CLI is not installed on this Windows workstation).
