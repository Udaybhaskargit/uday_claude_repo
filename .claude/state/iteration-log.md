# Iteration Log
<!-- Append-only. Do not edit or delete entries. -->

<!-- ENTRY FORMAT — Append one block per group iteration:

## Group {ID} — {Group Name}
- **Date:** {ISO 8601}
- **Status:** PASS | FAIL (attempt {N} of 3) | BLOCKED
- **Stories:** [{story IDs}]
- **Mode:** full | lean | solo | turbo
- **Summary:** {1-2 sentence description of what happened}
- **Checks:** {N} API, {N} Playwright, {N} design passed
- **Coverage:** {N}% (baseline: {N}%)
- **Learned Rules Applied:** [{rule numbers}]

### Micro-DAG (if agent team was used)
- Phase 1 (Independent): [{teammate IDs}]
- Phase 2 (Depends on Phase 1): [{teammate IDs}]
- Phase 3 (Integrators): [{teammate IDs}] (shared files: [{paths}])

-->

## Group A — Domain Foundation (Types layer)
- **Date:** 2026-09-06T18:11:32Z
- **Status:** PASS
- **Stories:** [E1-S1, E1-S2, E1-S3]
- **Mode:** full
- **Summary:** Implemented backend/src/types/ from scratch (enums, dataclass models, typed
  exceptions with HTTP-status mapping, and the centralized claim state-machine transition gate).
  Generator wrote 73 tests first (TDD), then implementation; evaluator independently re-ran all
  gates rather than trusting the self-report and traced every acceptance criterion in E1-S1/S2/S3
  to a specific failing-on-violation assertion. No blocking defects.
- **Checks:** 0 API, 0 Playwright, 0 design (Group A has no API/UI surface yet) — 4 architecture
  checks passed (layering, typing, folder structure, state-mutation gate), all 13 features (F001-F013)
  verified against acceptance criteria.
- **Coverage:** 100% (baseline: 0%)
- **Learned Rules Applied:** none (none exist yet)

### Notes
- Generator commit: `d00d4a5` "feat(types): implement Group A domain types layer (E1-S1, E1-S2, E1-S3)"
- Evaluator report: `specs/reviews/evaluator-report.md` (Group A section)
- Three generator deviations reviewed and accepted by evaluator as non-blocking: `enum.StrEnum`
  instead of `class X(str, Enum)` (required by ruff UP042 on py312 target); substituted
  `DOCS_VERIFIED` for the story text's non-canonical `SUBMIT_FNOL` event name in the terminal-state
  negative test (preserves AC intent); added `Policy.is_active_on(date)` ahead of its Group D story
  since it's already specified in data-models.md sec 2.1 and is a pure, zero-dependency method.
- Single-agent implementation (no cross-story file conflicts requiring a micro-DAG — E1-S1/S2 share
  models.py and E1-S1/S3 share enums.py, but the generator wrote both in one pass as a 3-story unit).
- Landed via branch `group-a/domain-types` + PR (capstone PR-only-merge rule), not a direct commit
  to main.

## Group B — Business Rule Configuration (Config layer)
- **Date:** 2026-09-06T00:00:00Z
- **Status:** PASS
- **Stories:** [E2-S1, E2-S2, E2-S3]
- **Mode:** full
- **Summary:** Implemented backend/src/config/ (fraud rule config loader, assessment rule config
  loader, AppConfig) plus the two declarative JSON config files. Generator extended Group A's bare
  `ConfigError` with an optional `variable_name` kwarg (additive, non-breaking). Evaluator
  independently re-ran all gates, verified the shipped JSON config files directly (not just
  in-memory test fixtures), mutation-tested the new import-layering test by injecting a temporary
  forbidden import, and confirmed the on-disk-edit-is-picked-up-on-reload behavior (E2-S1 AC4) with
  no module-level caching. No blocking defects.
- **Checks:** 0 API, 0 Playwright, 0 design (no API/UI surface yet) — architecture checks passed
  (Config imports only Types; one-way import rule mutation-tested), all 10 features (F014-F023)
  verified against acceptance criteria.
- **Coverage:** 100% (baseline: 100%) — full src/ tree (types + config), 359/359 statements
- **Learned Rules Applied:** none (none exist yet)

### Notes
- Generator commit: `51ff8b9` "implement Group B config layer" (backend/config/fraud-rules.json,
  assessment-rules.json; backend/src/config/{app_config,fraud_rules_config,assessment_rules_config}.py)
- Evaluator report: `specs/reviews/evaluator-report.md` (Group B section)
- Non-blocking observation from evaluator: neither config loader rejects negative/zero weights or
  thresholds structurally, since no AC requires it — left as-is.
- Landed via branch `group-b/config-layer` + PR (capstone PR-only-merge rule), not a direct commit
  to main.
