# Folder Structure — ClaimFlow

Top-level directory names (`backend/`, `frontend/`) are fixed by `.gitlab-ci.yml` and
`project-manifest.json` — do not rename. Every directory below maps onto exactly one layer of the
Types → Config → Repository → Service → API → UI chain (see `.claude/architecture.md`); the
one-way import rule applies across these directories.

```
capstone/
├── backend/                                # Layer: ALL backend layers. Fixed name (CI).
│   ├── requirements.txt                    # pip dependencies (fastapi, uvicorn, pydantic, pytest, ruff, mypy, coverage...)
│   ├── pyproject.toml                      # ruff + mypy configuration
│   ├── claimflow.db                        # SQLite file (git-ignored; created at startup/test time)
│   ├── config/                             # Declarative rule config consumed by the Config layer loaders
│   │   ├── fraud-rules.json                # E2-S1: 5 fraud rules + threshold (60)
│   │   └── assessment-rules.json           # E2-S2: per-claim-type deductible/co-pay + auto-approve ceiling (50000)
│   ├── migrations/                         # Layer: Repository (schema). E3-S1: numbered, append-only SQL
│   │   ├── 0001_create_policies.sql
│   │   ├── 0002_create_claims.sql
│   │   ├── 0003_create_claim_documents.sql
│   │   ├── 0004_create_fraud_screenings.sql
│   │   ├── 0005_create_assessments.sql
│   │   ├── 0006_create_decisions.sql
│   │   ├── 0007_create_settlements.sql
│   │   ├── 0008_create_claim_state_transitions.sql
│   │   └── 0009_create_admin_overrides.sql
│   ├── src/
│   │   ├── __init__.py
│   │   ├── main.py                         # FastAPI app factory; mounts all routers + /health
│   │   ├── types/                          # Layer: Types (Group A). Imports nothing else in src/.
│   │   │   ├── __init__.py
│   │   │   ├── enums.py                    # Role, ClaimType, PolicyStatus, ClaimStatus, DocumentType, VerificationStatus, DecisionOutcome, ReasonCode, ApiErrorCode, AdminOverrideCommand, transition events
│   │   │   ├── models.py                   # Policy, Claim, ClaimDocument, FraudScreening, Assessment, Decision, Settlement, ClaimStateTransition, AdminOverride, ActorContext (dataclasses, Decimal fields)
│   │   │   ├── exceptions.py               # PolicyNotActiveException, DuplicateClaimException, InvalidClaimStateException, UnknownClaimTypeError, ConfigError, ValidationError
│   │   │   └── state_machine.py            # E1-S2: TRANSITION_TABLE + transition(claim, event) -> ClaimStateTransition
│   │   ├── config/                         # Layer: Config (Group B). Imports: types only.
│   │   │   ├── __init__.py
│   │   │   ├── app_config.py               # E2-S3: AppConfig (db_path, backend_port, frontend_port, valid_roles)
│   │   │   ├── fraud_rules_config.py       # E2-S1: loads/validates config/fraud-rules.json
│   │   │   └── assessment_rules_config.py  # E2-S2: loads/validates config/assessment-rules.json
│   │   ├── db/                             # Layer: Repository (infra half). Imports: types, config.
│   │   │   ├── __init__.py
│   │   │   ├── connection.py               # sqlite3 connection factory (uses AppConfig.db_path)
│   │   │   └── migration_runner.py         # E3-S1: applies migrations/, checksum-verifies applied ones
│   │   ├── repositories/                   # Layer: Repository (Groups C/D). Imports: types, config, db.
│   │   │   ├── __init__.py
│   │   │   ├── policy_repository.py        # E3-S2: get_by_number(), is_active_on()
│   │   │   ├── claim_repository.py         # E3-S3: create(), apply_transition(), list_by_status_and_product(), exists_duplicate()
│   │   │   ├── claim_document_repository.py# supports E5-S1 checklist reads/writes
│   │   │   ├── fraud_screening_repository.py   # E3-S4: insert(), get_latest(); insert-only
│   │   │   ├── assessment_repository.py    # E3-S4: insert(), get_latest_assessment(); insert-only
│   │   │   ├── decision_repository.py      # E3-S4: insert(), get_latest(); insert-only
│   │   │   ├── settlement_repository.py    # E3-S4: insert(), list_all(); insert-only, no update()
│   │   │   └── admin_override_repository.py# E3-S4: insert(), list_admin_overrides(); insert-only
│   │   ├── services/                       # Layer: Service (Groups E/F/G/H/I). Imports: types, config, repositories.
│   │   │   ├── __init__.py
│   │   │   ├── fnol_intake_service.py      # E4-S1/S2/S3: submit_fnol(), policy-active + duplicate checks
│   │   │   ├── document_checklist_service.py # E5-S1: check_documents_complete(), verify_document()
│   │   │   ├── fraud_scoring_engine.py     # E5-S2: pure deterministic score(claim, config) -> (score, breakdown)
│   │   │   ├── fraud_screening_service.py  # E5-S3: run + persist FraudScreening, gate to ASSESSMENT/MANUAL_REVIEW
│   │   │   ├── assessment_service.py       # E6-S1: assess() -> Assessment (Decimal math, clamp >= 0)
│   │   │   ├── decision_engine.py          # E6-S2: decide(payable_amount, flagged) -> outcome + reason_code
│   │   │   ├── claim_pipeline_orchestrator.py # E6-S3: run_pipeline(), retry_pipeline(), PROCESSING_FAILED handling
│   │   │   ├── settlement_service.py       # E7-S1: settle(), stub payment trigger
│   │   │   ├── reopen_service.py           # E7-S2: reopen()
│   │   │   └── admin_override_service.py   # E8-S2: override()
│   │   ├── lib/                            # Cross-cutting (not a "layer" but importable by all)
│   │   │   ├── __init__.py
│   │   │   └── logger.py                   # structured JSON logging, no-PII guard (NFR-03/06)
│   │   └── api/                            # Layer: API (Groups C,G,H,I). Imports: types, config, repositories, services.
│   │       ├── __init__.py
│   │       ├── dependencies/
│   │       │   ├── __init__.py
│   │       │   └── auth.py                 # E8-S1: get_actor_context dependency, require_role(*roles)
│   │       ├── error_handlers.py           # E1-S3 AC4: exception -> HTTP status/code mapping, registered on the app
│   │       ├── schemas/                    # Pydantic request/response models (mirrors api-contracts.schema.json)
│   │       │   ├── __init__.py
│   │       │   ├── common_schemas.py       # ErrorResponse, shared enums-as-pydantic
│   │       │   ├── claims_schemas.py       # FnolRequest/Response, ClaimDetailResponse, ReopenResponse
│   │       │   ├── documents_schemas.py    # PendingDocsResponse, DocumentPatchRequest/Response
│   │       │   ├── workbench_schemas.py    # FraudAlertsResponse, WorkbenchResponse, DecisionRequest/Response
│   │       │   └── admin_schemas.py        # AdminClaimsResponse, PayoutsResponse, OverrideRequest/Response, RetryResponse
│   │       └── routers/
│   │           ├── __init__.py
│   │           ├── health_router.py        # GET /health
│   │           ├── claims_router.py        # E9-S1: POST/GET /api/claims, POST /api/claims/{id}/reopen
│   │           ├── documents_router.py     # E9-S2: GET .../documents/pending, PATCH .../documents/{type}
│   │           ├── workbench_router.py     # E9-S3: GET .../fraud-alerts, GET .../workbench, POST .../decision
│   │           └── admin_router.py         # E9-S4: GET/POST /api/admin/*
│   └── tests/
│       ├── conftest.py                     # fixtures: temp sqlite db, seeded policies/claims, TestClient
│       ├── unit/
│       │   ├── types/                      # state machine + exception unit tests
│       │   ├── config/                     # config loader unit tests
│       │   ├── repositories/               # repository unit tests (incl. "no update/delete" structural checks)
│       │   └── services/                   # service unit tests, one file per service module above
│       ├── integration/
│       │   └── api/                        # one file per router, full request/response cycle via TestClient
│       └── architecture/                   # NFR-08: structural tests
│           ├── test_layer_imports.py       # asserts one-way import direction across src/*
│           └── test_state_mutation_gate.py # asserts no `.status =` assignment outside state_machine.py
│
└── frontend/                               # Layer: UI (+ frontend's own thin API-client layer). Fixed name (CI).
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    ├── playwright.config.ts
    ├── eslint.config.js
    ├── index.html
    ├── src/
    │   ├── main.tsx                        # React root, router setup
    │   ├── App.tsx                         # top-level route table, role-based redirects
    │   ├── types/                          # Layer: Types (frontend mirror). Imports nothing else in src/.
    │   │   ├── enums.ts                    # Role, ClaimType, ClaimStatus, DocumentType, VerificationStatus, DecisionOutcome, ReasonCode
    │   │   └── models.ts                   # Claim, ClaimDocument, FraudScreening, Assessment, Decision, Settlement, AdminOverride (TS interfaces mirroring data-models.schema.json)
    │   ├── config/                         # Layer: Config. Imports: types.
    │   │   └── env.ts                      # API base URL (from Vite env), read once here only
    │   ├── api/                            # Layer: API (client-side). Imports: types, config.
    │   │   ├── httpClient.ts               # fetch wrapper: attaches X-Role/X-Actor-Id, parses ErrorResponse envelope
    │   │   ├── claimsApi.ts                # wraps E9-S1 endpoints
    │   │   ├── documentsApi.ts             # wraps E9-S2 endpoints
    │   │   ├── workbenchApi.ts             # wraps E9-S3 endpoints
    │   │   └── adminApi.ts                 # wraps E9-S4 endpoints
    │   ├── context/
    │   │   └── AuthContext.tsx             # stub role/actor-id selector; provides current ActorContext app-wide
    │   ├── components/                     # Layer: UI (shared, presentational). Imports: types, config.
    │   │   ├── RoleGuard.tsx               # renders "access denied" when role context doesn't match a route's requirement
    │   │   ├── StatusBadge.tsx
    │   │   ├── ReasonCodeText.tsx          # maps ReasonCode -> human-readable copy
    │   │   ├── ConfirmDialog.tsx
    │   │   └── QueueTable.tsx              # generic sortable/filterable table used by all four internal queues
    │   ├── features/                       # Layer: UI (role-scoped feature modules). Imports: types, api, components.
    │   │   ├── customer/
    │   │   │   ├── FnolForm.tsx            # E10-S1
    │   │   │   ├── ClaimTracker.tsx        # E10-S2
    │   │   │   └── DisputeAction.tsx       # E10-S3
    │   │   ├── assessor/
    │   │   │   ├── DocumentVerificationQueue.tsx # E11-S1
    │   │   │   ├── FraudAlertQueue.tsx     # E11-S2
    │   │   │   └── AssessorWorkbench.tsx   # E11-S3
    │   │   └── admin/
    │   │       └── AdminDashboard.tsx      # E11-S4
    │   └── pages/                          # Route-level composition (wraps a feature + RoleGuard + layout chrome)
    │       ├── RoleSelectPage.tsx          # stub "login" — choose role + actor id
    │       ├── CustomerFnolPage.tsx
    │       ├── CustomerTrackerPage.tsx
    │       ├── DocumentQueuePage.tsx
    │       ├── FraudQueuePage.tsx
    │       ├── WorkbenchPage.tsx
    │       └── AdminDashboardPage.tsx
    └── tests/
        ├── unit/                           # vitest: one file per component/feature above
        └── e2e/                            # Playwright specs, one per end-to-end user journey (FNOL->tracker, doc-verify->fraud->workbench->decision, admin override, dispute/reopen)
```

## Notes on the mapping to layers

- **Types** (`backend/src/types/`, `frontend/src/types/`) import nothing from any other directory
  under `src/`.
- **Config** (`backend/src/config/`, `frontend/src/config/`) import only from `types/`.
- **Repository** (`backend/src/db/`, `backend/src/repositories/`) import only from `types/` and
  `config/`. Frontend has no repository layer — the browser has no direct DB access.
- **Service** (`backend/src/services/`) imports only from `types/`, `config/`, `repositories/`.
  Frontend has no service layer of its own; `frontend/src/api/` plays the equivalent client-side
  boundary role (never call `fetch` outside this directory).
- **API** (`backend/src/api/`) imports from all backend layers below it. `frontend/src/api/`
  imports only `types/` and `config/`.
- **UI** (`frontend/src/components/`, `features/`, `pages/`) imports `types/`, `config/`, and
  `api/` — never reaches into backend code directly (there is no shared package; the two apps
  communicate only over HTTP).
- `backend/src/lib/` and its frontend absence are intentional: cross-cutting logging lives only on
  the backend (the only place that ever touches PII-adjacent data or writes logs).
