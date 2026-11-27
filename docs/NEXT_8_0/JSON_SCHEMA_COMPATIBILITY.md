# GRANDEC NEXT 8.0 — Authoring JSON Schema 1.0 Compatibility

## Service Location
- Module: `apps/tests/package_service.py`
- Studio Endpoints:
  - `POST /api/v1/teacher/studio/package/validate/`
  - `POST /api/v1/teacher/studio/package/import/`
  - `GET /api/v1/teacher/studio/tests/<id>/package/` (`?keyless=1` strips all answer keys cleanly)
  - `GET /api/v1/teacher/studio/tests/<id>/readiness/`

## Supported Structure & Round-Trip Behavior
- **Top-level fields**: `schemaVersion: "1.0"`, `title`, `subject`, `examType` (`ielts_academic` | `ielts_general` | `cefr_multilevel`), `assessmentCategory`, `timeLimitMinutes`, `sections[]`.
- **Sections -> Parts -> Groups -> Questions**:
  - Preserves `code`, `partNumber`, `audioPlayLimit`, `audioDurationSec`, `transcript`, `contentLayout`, `stimulusRef` (`EX4-402` identity separation so identical passage bodies with distinct `stimulusRef` stay distinct DB rows).
  - Supports canonical uppercase & lowercase question types (`SINGLE_CHOICE`, `MULTIPLE_CHOICE`, `TRUE_FALSE_NOT_GIVEN`, `YES_NO_NOT_GIVEN`, `HEADING_MATCHING`, `MATCHING`, `GAP_FILL`, `MAP_LABELING`, `TEXT_MATCH`, `SHORT_ANSWER`, `WRITTEN`, `SPEAKING_PROMPT`).
  - Supports per-question `maxScore`, `evidenceText`, `audioStartSec`, `cefrLevel`, `skillTags`.
- **Safety Gates**:
  - Validation fails transactionally before creating partial DB rows if schema errors exist.
  - Mock publish readiness blocks incomplete `full_mock` exams missing required skills, audio, or valid question counts.
  - Exported keyless templates remove `isCorrect`, `correctText`, `acceptedAnswers`, and gap-fill keys (`tests/test_next8_phase3_builder.py`).
