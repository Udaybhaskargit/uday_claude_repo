# Component Map — ClaimFlow

Maps every one of the 34 stories (epics E1–E11) to the specific files (from `folder-structure.md`)
that implement it. Test file locations are included so `/test`/`test-engineer` agents can co-locate
AC-tagged tests without re-deriving paths. Paths are relative to `capstone/`.

| Story | Title | Layer / Group | Primary files created/modified | Test files |
|---|---|---|---|---|
| E1-S1 | Define core domain types and enums | Types / A | `backend/src/types/enums.py`, `backend/src/types/models.py` | `backend/tests/unit/types/test_enums.py`, `backend/tests/unit/types/test_models.py` |
| E1-S2 | Build the claim state machine transition gate | Types / A | `backend/src/types/state_machine.py`, `backend/src/types/models.py` (`ClaimStateTransition`) | `backend/tests/unit/types/test_state_machine.py`, `backend/tests/architecture/test_state_mutation_gate.py` |
| E1-S3 | Define reason codes and domain exceptions | Types / A | `backend/src/types/enums.py` (`ReasonCode`), `backend/src/types/exceptions.py` | `backend/tests/unit/types/test_exceptions.py` |
| E2-S1 | Load fraud rule configuration from declarative config | Config / B | `backend/config/fraud-rules.json`, `backend/src/config/fraud_rules_config.py` | `backend/tests/unit/config/test_fraud_rules_config.py` |
| E2-S2 | Load deductible, co-pay, and decision threshold configuration | Config / B | `backend/config/assessment-rules.json`, `backend/src/config/assessment_rules_config.py` | `backend/tests/unit/config/test_assessment_rules_config.py` |
| E2-S3 | Centralize application and role configuration | Config / B | `backend/src/config/app_config.py` | `backend/tests/unit/config/test_app_config.py` |
| E3-S1 | Write append-only numbered SQLite migrations | Repository / C | `backend/migrations/0001_create_policies.sql` … `0009_create_admin_overrides.sql`, `backend/src/db/migration_runner.py`, `backend/src/db/connection.py` | `backend/tests/unit/repositories/test_migration_runner.py` |
| E3-S2 | Build the policy repository | Repository / D | `backend/src/repositories/policy_repository.py` | `backend/tests/unit/repositories/test_policy_repository.py` |
| E3-S3 | Build the claim repository | Repository / D | `backend/src/repositories/claim_repository.py`, `backend/src/repositories/claim_document_repository.py` | `backend/tests/unit/repositories/test_claim_repository.py` |
| E3-S4 | Build the append-only audit repositories | Repository / D | `backend/src/repositories/fraud_screening_repository.py`, `assessment_repository.py`, `decision_repository.py`, `settlement_repository.py`, `admin_override_repository.py` | `backend/tests/unit/repositories/test_audit_repositories.py` |
| E4-S1 | Implement the FNOL intake service | Service / E | `backend/src/services/fnol_intake_service.py` | `backend/tests/unit/services/test_fnol_intake_service.py` |
| E4-S2 | Enforce policy-active validation at incident date | Service / F | `backend/src/services/fnol_intake_service.py`, `backend/src/types/exceptions.py` (`PolicyNotActiveException`) | `backend/tests/unit/services/test_fnol_intake_service.py` |
| E4-S3 | Detect and reject duplicate FNOL submissions | Service / F | `backend/src/services/fnol_intake_service.py`, `backend/src/repositories/claim_repository.py` (`exists_duplicate`) | `backend/tests/unit/services/test_fnol_intake_service.py` |
| E5-S1 | Enforce the per-claim-type document checklist | Service / F | `backend/src/services/document_checklist_service.py` | `backend/tests/unit/services/test_document_checklist_service.py` |
| E5-S2 | Implement the deterministic fraud scoring engine | Service / E | `backend/src/services/fraud_scoring_engine.py` | `backend/tests/unit/services/test_fraud_scoring_engine.py` |
| E5-S3 | Persist fraud screenings and gate the pipeline | Service / F | `backend/src/services/fraud_screening_service.py` | `backend/tests/unit/services/test_fraud_screening_service.py` |
| E6-S1 | Implement the assessment service | Service / E | `backend/src/services/assessment_service.py` | `backend/tests/unit/services/test_assessment_service.py` |
| E6-S2 | Implement the decision engine | Service / G | `backend/src/services/decision_engine.py` | `backend/tests/unit/services/test_decision_engine.py` |
| E6-S3 | Orchestrate the claim pipeline with failure handling | Service / H | `backend/src/services/claim_pipeline_orchestrator.py`, `backend/src/lib/logger.py` | `backend/tests/unit/services/test_claim_pipeline_orchestrator.py` |
| E7-S1 | Implement the settlement service | Service / I | `backend/src/services/settlement_service.py` | `backend/tests/unit/services/test_settlement_service.py` |
| E7-S2 | Implement the reopen/dispute service | Service / E | `backend/src/services/reopen_service.py` | `backend/tests/unit/services/test_reopen_service.py` |
| E8-S1 | Implement the stubbed role-based auth dependency | API / C | `backend/src/api/dependencies/auth.py` | `backend/tests/integration/api/test_auth_dependency.py` |
| E8-S2 | Implement the admin override service | Service / E | `backend/src/services/admin_override_service.py` | `backend/tests/unit/services/test_admin_override_service.py` |
| E9-S1 | Expose the claims API for intake, tracking, and dispute | API / I | `backend/src/api/routers/claims_router.py`, `backend/src/api/schemas/claims_schemas.py` | `backend/tests/integration/api/test_claims_router.py` |
| E9-S2 | Expose the document verification API | API / G | `backend/src/api/routers/documents_router.py`, `backend/src/api/schemas/documents_schemas.py` | `backend/tests/integration/api/test_documents_router.py` |
| E9-S3 | Expose the assessor workbench API | API / H | `backend/src/api/routers/workbench_router.py`, `backend/src/api/schemas/workbench_schemas.py` | `backend/tests/integration/api/test_workbench_router.py` |
| E9-S4 | Expose the admin API for queues, overrides, and audit trail | API / F | `backend/src/api/routers/admin_router.py`, `backend/src/api/schemas/admin_schemas.py` | `backend/tests/integration/api/test_admin_router.py` |
| E10-S1 | Build the FNOL submission form | UI / J | `frontend/src/features/customer/FnolForm.tsx`, `frontend/src/pages/CustomerFnolPage.tsx`, `frontend/src/api/claimsApi.ts` | `frontend/tests/unit/FnolForm.test.tsx`, `frontend/tests/e2e/fnol-submission.spec.ts` |
| E10-S2 | Build the claim tracker view | UI / J | `frontend/src/features/customer/ClaimTracker.tsx`, `frontend/src/pages/CustomerTrackerPage.tsx`, `frontend/src/components/ReasonCodeText.tsx` | `frontend/tests/unit/ClaimTracker.test.tsx`, `frontend/tests/e2e/claim-tracker.spec.ts` |
| E10-S3 | Build the dispute action flow | UI / K | `frontend/src/features/customer/DisputeAction.tsx`, `frontend/src/components/ConfirmDialog.tsx` | `frontend/tests/unit/DisputeAction.test.tsx`, `frontend/tests/e2e/dispute-flow.spec.ts` |
| E11-S1 | Build the document verification queue UI | UI / H | `frontend/src/features/assessor/DocumentVerificationQueue.tsx`, `frontend/src/pages/DocumentQueuePage.tsx`, `frontend/src/api/documentsApi.ts` | `frontend/tests/unit/DocumentVerificationQueue.test.tsx`, `frontend/tests/e2e/document-queue.spec.ts` |
| E11-S2 | Build the fraud alert queue UI | UI / I | `frontend/src/features/assessor/FraudAlertQueue.tsx`, `frontend/src/pages/FraudQueuePage.tsx`, `frontend/src/api/workbenchApi.ts` | `frontend/tests/unit/FraudAlertQueue.test.tsx`, `frontend/tests/e2e/fraud-queue.spec.ts` |
| E11-S3 | Build the assessor workbench UI | UI / J | `frontend/src/features/assessor/AssessorWorkbench.tsx`, `frontend/src/pages/WorkbenchPage.tsx` | `frontend/tests/unit/AssessorWorkbench.test.tsx`, `frontend/tests/e2e/assessor-workbench.spec.ts` |
| E11-S4 | Build the admin dashboard UI | UI / G | `frontend/src/features/admin/AdminDashboard.tsx`, `frontend/src/pages/AdminDashboardPage.tsx`, `frontend/src/api/adminApi.ts` | `frontend/tests/unit/AdminDashboard.test.tsx`, `frontend/tests/e2e/admin-dashboard.spec.ts` |

## Cross-cutting / shared files (not tied to a single story)

| File | Used by |
|---|---|
| `backend/src/main.py` | All API stories (E8-S1, E9-S1..S4) — mounts routers and registers `error_handlers.py` |
| `backend/src/api/error_handlers.py` | E1-S3 (exception→status mapping), all API routers |
| `backend/src/api/schemas/common_schemas.py` | All API routers (shared `ErrorResponse` envelope) |
| `backend/tests/architecture/test_layer_imports.py` | All stories — NFR-08 one-way-import structural check |
| `frontend/src/api/httpClient.ts` | All frontend `*Api.ts` modules — attaches `X-Role`/`X-Actor-Id`, parses error envelope |
| `frontend/src/context/AuthContext.tsx` | All UI stories — stub role/actor-id selection (`frontend/src/pages/RoleSelectPage.tsx`) |
| `frontend/src/components/RoleGuard.tsx` | E11-S1, E11-S2, E11-S3, E11-S4 (access-denied states), and route guards generally |
| `frontend/src/components/QueueTable.tsx` | E11-S1, E11-S2, E11-S4 (shared queue rendering) |

## Verification against the quality gate

All 34 story IDs from `specs/stories/dependency-graph.md` appear exactly once as a row above.
