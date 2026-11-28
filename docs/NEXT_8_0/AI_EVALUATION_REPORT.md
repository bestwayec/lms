# GRANDEC NEXT 8.0 — AI Evaluation Architecture & Honesty Report

## Core Integrity Safeguards
1. **Zero Fabricated Scores**:
   - Insufficient responses (`is_insufficient_response`, `<12` English words via `MIN_WRITING_EVIDENCE_WORDS`) raise `PreValidationError` (`400`, `RESULT_INSUFFICIENT_RESPONSE_EVIDENCE`) prior to billing or AI evaluation.
   - Missing API keys / circuit failures return HTTP `503` (`code: "not_graded"`) and release/refund student quota (`refund_feature_cap` / `release_usage`), storing no invented band or feedback (`apps/speaking/services.py`, `apps/essays/services.py`, `apps/webapi/views_essays.py`).
2. **Character-Offset Evidence Grounding & Repeated Phrase Disambiguation (`apps/core/ai_gateway.py`)**:
   - `find_grounded_offset()` and `verify_evidence_items()` verify every AI-cited quote and correction against the student's raw essay text using exact match, case-insensitive match, Unicode quote/whitespace-tolerant alignment, tight context-window hint scoring, and unused-span tracking so repeated phrases resolve distinctly. Unmatched fabrications are flagged `quote_verified: False` (`start_offset = -1`) and dropped/marked unverified.
3. **Honest Pronunciation Policy (`apps/speaking/`)**:
   - `SpeakingSubmission.pronunciation_score` is nullable (`null=True, blank=True`).
   - When evaluation runs in `transcript_only` mode without acoustic audio telemetry (`pronunciation_score = None`), the system stores `pronunciation_score = None`, leaves `overall_band = None` and `final_score = None` rather than presenting a 3-criterion transcript average as a complete IELTS Speaking band, records `feedback["is_partial_estimate"] = True` and `feedback["partial_band_estimate"]`, and displays `"—"` in `SpeakingResult.tsx` & `pdf_generator.py` with an explicit partial-assessment notice.
4. **Audio Duration & Container Decoding (`apps/speaking/audio_verify.py`)**:
   - PyAV (`av>=14.0,<20.0`) is declared in `requirements/base.txt` (`av==19.0.2` verified locally with `opus` codec + `webm` container support).
   - Model-free bounded subprocess (`python -m apps.speaking.audio_verify`, 20s timeout) validates WAV headers via Python stdlib `wave` and WebM/OGG/MP3/M4A containers via PyAV across uploads `>= 44` bytes (enforcing `[expected - 1.0s, expected + 0.5s]` when expected duration is configured, while supporting Teacher-review CBT WebM/Opus recordings).
   - Rejects empty (`SPEAKING_AUDIO_EMPTY`) and corrupt (`SPEAKING_AUDIO_DURATION_INVALID` / `SPEAKING_AUDIO_INVALID_CONTAINER`) recordings before quota deduction.
5. **AI Gateway Observability & Cost Control (`apps/core/ai_gateway.py`, `views_panel.py`)**:
   - Tracks per-feature call volume, success/failure counts, tokens in/out, USD cost, latency, and circuit-breaker state (`ai_health:open:*`) exposed strictly to platform admins at `GET /api/v1/panel/ai-metrics/`.
