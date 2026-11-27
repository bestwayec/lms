# GRANDEC NEXT 8.0 — AI Calibration, Cost & Honesty Limitations Report

## What Was Verified
1. **Honest Refusal & Quota Refund**:
   - Short writing (`<10` words) returns `400 code="rejected"`.
   - Missing/unavailable AI providers return `503 code="not_graded"` with automatic allowance refund (`enforce_essay_quota`/`release_usage` and `consume_feature_cap`/`refund_feature_cap`).
2. **Evidence Grounding (`apps/core/ai_gateway.py`)**:
   - Quoted snippets in AI criterion responses are matched against the exact submitted text to populate `start_offset`, `end_offset`, and `quote_verified`. Unverified hallucinations receive `quote_verified = False`, `start_offset = -1`.
3. **Speaking Pronunciation Honesty**:
   - Transcript-only evaluations store `pronunciation_score = None` (`not_measured_from_transcript`) instead of synthesizing acoustic scores.
   - Audio uploads undergo local WAV/container integrity and bounded duration checks (`apps/speaking/audio_verify.py`).
4. **Calibration Utility**:
   - `compute_calibrated_stats()` verifies MAE and within-0.5-band accuracy on anchor pairs (`tests/test_next8_phase6_7_writing.py`).

## Explicit Limitations (Disclosed Honestly)
- Live external LLM calls (OpenRouter `deepseek/deepseek-r1-0528` & `fish-audio/s2.1-pro-free:free` STT / Gemini multimodal fallback) were **not** executed against paid external API keys during automated CI/local test runs; automated test coverage exercises mocked provider contracts + explicit fault/unavailable/calibration paths + `ESSAY_AI_MOCK_MODE=True` where explicitly requested.
- Therefore, live production AI examiner agreement (`MAE` against real certified IELTS/BMB human raters across large live cohorts) must be measured iteratively post-deployment using `TeacherReview` vs AI score logs and the Admin Cost Control panel (`/api/v1/panel/ai-metrics/`).
- Automated `av` decoding for `.webm` / `.ogg` blobs requires PyAV (`av`) in the container image; WAV files decode deterministically via Python stdlib `wave`.
