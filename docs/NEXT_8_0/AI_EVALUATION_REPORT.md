# GRANDEC NEXT 8.0 — AI Evaluation Architecture & Honesty Report

## Core Integrity Safeguards
1. **Zero Fabricated Scores**:
   - Insufficient responses (`is_insufficient_response`, `<10` English words) raise `PreValidationError` (`400`, `RESULT_INSUFFICIENT_RESPONSE_EVIDENCE`) prior to billing or AI evaluation.
   - Missing API keys / circuit failures return HTTP `503` (`code: "not_graded"`) and release/refund student quota (`refund_feature_cap` / `release_usage`), storing no invented band or feedback (`apps/speaking/services.py`, `apps/essays/services.py`, `apps/webapi/views_essays.py`).
2. **Character-Offset Evidence Grounding (`apps/core/ai_gateway.py`)**:
   - `find_grounded_offset()` and `verify_evidence_items()` verify every AI-cited quote against the student's raw essay text using exact match, case-insensitive match, and whitespace-collapsed regex alignment, recording `start_offset`, `end_offset`, and `quote_verified: bool`. Unmatched fabrications are flagged `quote_verified: False` (`start_offset = -1`).
3. **Honest Pronunciation Policy (`apps/speaking/`)**:
   - `SpeakingSubmission.pronunciation_score` is nullable (`null=True, blank=True`).
   - When evaluation runs in `transcript_only` mode without acoustic audio telemetry (`pronunciation_score: None`), the system stores `pronunciation_score = None`, marks `feedback["pronunciation_status"] = "not_measured_from_transcript"`, displays `"—"` in `SpeakingResult.tsx` & `pdf_generator.py`, and averages `overall_band` over the 3 text-verifiable criteria (`FC`, `LR`, `GRA`).
4. **Audio Duration & Integrity Verification (`apps/speaking/audio_verify.py`)**:
   - Model-free bounded subprocess (`python -m apps.speaking.audio_verify`, 20s timeout) validates WAV container headers via Python stdlib `wave` (`8000–192000 Hz`, aligned frames, frame count match) and optional `av`, enforcing `[expected - 1.0s, expected + 0.5s]` when an expected duration is required.
   - Rejects empty (`SPEAKING_AUDIO_EMPTY`), non-audio/corrupt (`SPEAKING_AUDIO_DURATION_INVALID` / `SPEAKING_AUDIO_INVALID_CONTAINER`), and out-of-window recordings before quota deduction.
5. **AI Gateway Observability & Cost Control (`apps/core/ai_gateway.py`, `views_panel.py`)**:
   - Tracks per-feature call volume, success/failure counts, tokens in/out, USD cost, latency, and circuit-breaker state (`ai_health:open:*`) exposed strictly to platform admins at `GET /api/v1/panel/ai-metrics/`.
