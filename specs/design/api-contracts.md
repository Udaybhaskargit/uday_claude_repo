# API Contracts — ClaimFlow

Base URL (local dev): `http://localhost:8000`. All endpoints are prefixed `/api` except the health
check. Companion machine-readable contract: `specs/design/api-contracts.schema.json` (OpenAPI
3.0). Request/response bodies are JSON (`Content-Type: application/json`) unless noted.

## Conventions used throughout this document

- **Auth headers** — every route except `GET /health` requires:
  - `X-Role: CUSTOMER | ASSESSOR | ADMIN`
  - `X-Actor-Id: <string>` — an arbitrary stable identifier for the acting user (e.g.
    `"cust-1001"`, `"assessor-3"`, `"admin-1"`). Not validated against a user table; this is the
    E8-S1 stub auth boundary (BRD §7.1) — **not production-grade authentication**. No JWT/OAuth.
  - Resolved into `ActorContext(role, actor_id)` and injected into the route handler.
- **Money fields** are decimal strings (e.g. `"35000.00"`), never JSON floats (NFR-01).
- **Dates** are `YYYY-MM-DD`; **timestamps** are ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`).
- **Rate limits:** N/A — single-operator local demo (BRD §11 operational constraints).
- **Error envelope** (uniform across all endpoints):
  ```json
  {
    "error": {
      "code": "POLICY_INACTIVE",
      "message": "Policy POL-MOTOR-0001 is not active on 2026-03-10.",
      "details": {}
    }
  }
  ```
  `code` is one of the `ApiErrorCode` values in `data-models.md` §1. `details` is an optional
  object with extra context (e.g. `policy_number`, `incident_date`).
- **Standard error statuses used across all authenticated routes:**
  | Status | When |
  |---|---|
  | 401 | `X-Role` header missing, or its value is not one of `AppConfig.valid_roles` (E8-S1 AC2/AC3) |
  | 403 | Valid role, but not one of the roles the route's `require_role(...)` allows (E8-S1 AC4) |
  | 404 | Path references a claim/entity id that does not exist |
  | 409 | Domain conflict — duplicate claim, or invalid state transition attempted |
  | 422 | Domain validation failure — inactive policy, missing mandatory field (e.g. reason code) |
  | 500 | Never expected in normal operation; unexpected mid-pipeline errors are caught and routed to `PROCESSING_FAILED` (E6-S3) rather than surfaced as raw 500s to callers of `/api/claims` |

---

## Health

### `GET /health`

- **Purpose:** liveness/readiness probe (NFR-07: responds 200 within 1s of successful startup).
- **Auth:** none.
- **Request:** no params, no body.
- **Response `200 OK`:**
  ```json
  { "status": "ok" }
  ```
- **Errors:** none defined (the process is either up and returns 200, or is not reachable).
- **Rate limits:** N/A.

---

## Claims API (E9-S1) — Customer role

### `POST /api/claims`

- **Purpose:** submit a First Notice of Loss (FNOL) for motor, health, or life (E4-S1..S3).
- **Auth:** `require_role(CUSTOMER)`.
- **Headers:** `X-Role: CUSTOMER`, `X-Actor-Id: <customer actor id>`.
- **Request body:**
  ```json
  {
    "policy_number": "POL-MOTOR-0001",
    "claim_type": "MOTOR",
    "incident_date": "2026-03-10",
    "claim_amount": "40000.00"
  }
  ```
  | Field | Type | Required | Notes |
  |---|---|---|---|
  | `policy_number` | string | yes | must reference an existing `Policy` |
  | `claim_type` | `MOTOR｜HEALTH｜LIFE` | yes | drives the generated document checklist |
  | `incident_date` | date | yes | must fall within the policy's active window (E4-S2) |
  | `claim_amount` | decimal string | yes | > 0 |
- **Response `201 Created`:**
  ```json
  {
    "claim_id": 42,
    "status": "DOCS_PENDING",
    "checklist": [
      { "document_type": "POLICE_FIR", "verification_status": "MISSING" },
      { "document_type": "INVOICE", "verification_status": "MISSING" }
    ]
  }
  ```
- **Errors:**
  | Status | code | Condition |
  |---|---|---|
  | 422 | `POLICY_INACTIVE` | Policy not `ACTIVE` at `incident_date` (E4-S2 AC4) |
  | 404 | `NOT_FOUND` | `policy_number` does not exist |
  | 409 | `DUPLICATE_CLAIM` | A non-void claim already exists for `(policy_number, incident_date)` (E4-S3 AC3) |
  | 422 | `VALIDATION_ERROR` | Missing/malformed field, unknown `claim_type` |
- **Rate limits:** N/A.

### `GET /api/claims/{id}`

- **Purpose:** claim tracker read model (E10-S2): status, decision, reason codes, missing docs.
- **Auth:** `require_role(CUSTOMER, ASSESSOR, ADMIN)` — any authenticated role may read a claim by
  id; ownership scoping is out of scope (BRD §7.1 — no real identity provider to check ownership
  against).
- **Path params:** `id` — claim id (integer).
- **Response `200 OK`:**
  ```json
  {
    "claim_id": 42,
    "claim_type": "MOTOR",
    "status": "MANUAL_REVIEW",
    "incident_date": "2026-03-10",
    "claim_amount": "75000.00",
    "missing_documents": [],
    "decision": {
      "outcome": "MANUAL_REVIEW",
      "reason_code": "HIGH_VALUE_REVIEW",
      "decided_by": "system",
      "created_at": "2026-03-11T09:04:00Z"
    },
    "settlement": null,
    "parent_claim_id": null
  }
  ```
  `decision` is `null` until a `Decision` row exists. `settlement` is `null` until a `Settlement`
  row exists.
- **Errors:**
  | Status | code | Condition |
  |---|---|---|
  | 404 | `NOT_FOUND` | claim id does not exist |
- **Rate limits:** N/A.

### `POST /api/claims/{id}/reopen`

- **Purpose:** dispute a `SETTLED` claim (E7-S2, E10-S3).
- **Auth:** `require_role(CUSTOMER)`.
- **Path params:** `id` — the `SETTLED` claim's id.
- **Request body:** none required (empty object accepted for extensibility).
- **Response `201 Created`:**
  ```json
  { "sub_claim_id": 99, "parent_claim_id": 42, "status": "INTAKE" }
  ```
- **Errors:**
  | Status | code | Condition |
  |---|---|---|
  | 404 | `NOT_FOUND` | claim id does not exist |
  | 409 | `INVALID_STATE_TRANSITION` | claim is not currently `SETTLED` (E7-S2 AC4) |
- **Rate limits:** N/A.

---

## Document Verification API (E9-S2) — Assessor role

### `GET /api/claims/documents/pending`

- **Purpose:** internal queue of claims in `DOCS_PENDING` with outstanding checklist items
  (E11-S1).
- **Auth:** `require_role(ASSESSOR, ADMIN)`.
- **Query params:** `claim_type` (optional, `MOTOR｜HEALTH｜LIFE`) — filter the queue.
- **Response `200 OK`:**
  ```json
  {
    "claims": [
      {
        "claim_id": 42,
        "claim_type": "MOTOR",
        "outstanding_documents": ["POLICE_FIR"]
      }
    ]
  }
  ```
- **Errors:** none beyond the standard auth statuses.
- **Rate limits:** N/A.

### `PATCH /api/claims/{id}/documents/{type}`

- **Purpose:** toggle a checklist item to `VERIFIED`/`MISSING`; auto-advances the claim to
  `FRAUD_SCREENING` once every item for its claim type is `VERIFIED` (E5-S1).
- **Auth:** `require_role(ASSESSOR, ADMIN)` — `CUSTOMER` gets 403 (E9-S2 AC3).
- **Path params:** `id` — claim id; `type` — one `DocumentType` value, must belong to the claim's
  own checklist (E5-S1 AC4).
- **Request body:**
  ```json
  { "verification_status": "VERIFIED" }
  ```
- **Response `200 OK`:**
  ```json
  {
    "claim_id": 42,
    "document_type": "POLICE_FIR",
    "verification_status": "VERIFIED",
    "claim_status": "FRAUD_SCREENING"
  }
  ```
  `claim_status` reflects the claim's status *after* this update (may still be `DOCS_PENDING` if
  other items remain outstanding).
- **Errors:**
  | Status | code | Condition |
  |---|---|---|
  | 404 | `NOT_FOUND` | claim id or document type row does not exist |
  | 422 | `VALIDATION_ERROR` | `type` is not part of this claim's own checklist |
  | 403 | `FORBIDDEN` | caller role is `CUSTOMER` |
- **Rate limits:** N/A.

---

## Assessor Workbench API (E9-S3) — Assessor role

### `GET /api/claims/fraud-alerts`

- **Purpose:** queue of claims whose latest `FraudScreening.flagged == True` (E11-S2).
- **Auth:** `require_role(ASSESSOR, ADMIN)`.
- **Query params:** none.
- **Response `200 OK`:**
  ```json
  {
    "claims": [
      {
        "claim_id": 42,
        "claim_type": "MOTOR",
        "fraud_score": 65,
        "triggered_rules": ["HIGH_CLAIM_TO_SUM_RATIO", "EARLY_FILING"]
      }
    ]
  }
  ```
- **Errors:** none beyond standard auth statuses.
- **Rate limits:** N/A.

### `GET /api/claims/{id}/workbench`

- **Purpose:** claim detail for assessor review: fraud score/breakdown, assessed
  `payable_amount`, decision-rationale fields (E11-S3).
- **Auth:** `require_role(ASSESSOR, ADMIN)`.
- **Path params:** `id` — claim id (expected to be in `MANUAL_REVIEW`, but the route does not
  reject other statuses — the UI decides what to render).
- **Response `200 OK`:**
  ```json
  {
    "claim_id": 42,
    "claim_type": "MOTOR",
    "status": "MANUAL_REVIEW",
    "fraud_screening": { "score": 65, "threshold": 60, "flagged": true,
      "breakdown": [ {"rule_name": "HIGH_CLAIM_TO_SUM_RATIO", "weight": 40},
                     {"rule_name": "EARLY_FILING", "weight": 25} ] },
    "assessment": { "claim_amount": "75000.00", "sum_insured": "100000.00",
      "deductible": "5000.00", "co_pay": "0.00", "payable_amount": "70000.00" },
    "suggested_reason_code": "HIGH_VALUE_REVIEW"
  }
  ```
- **Errors:**
  | Status | code | Condition |
  |---|---|---|
  | 404 | `NOT_FOUND` | claim id does not exist |
- **Rate limits:** N/A.

### `POST /api/claims/{id}/decision`

- **Purpose:** assessor submits a manual decision on a `MANUAL_REVIEW` claim (E6-S2, E11-S3).
- **Auth:** `require_role(ASSESSOR)`.
- **Path params:** `id` — claim id.
- **Request body:**
  ```json
  { "outcome": "AUTO_APPROVE", "reason_code": "AUTO_APPROVED_LOW_RISK" }
  ```
  | Field | Type | Required | Notes |
  |---|---|---|---|
  | `outcome` | `DecisionOutcome` | yes | `AUTO_APPROVE｜MANUAL_REVIEW｜REJECT` |
  | `reason_code` | `ReasonCode` | yes | must be a value from the closed `ReasonCode` set |
- **Response `200 OK`:**
  ```json
  {
    "claim_id": 42,
    "decision": { "outcome": "AUTO_APPROVE", "reason_code": "AUTO_APPROVED_LOW_RISK",
      "decided_by": "assessor-3", "created_at": "2026-03-11T10:00:00Z" },
    "claim_status": "AUTO_APPROVED"
  }
  ```
  `decided_by` is set from `X-Actor-Id` (E6-S2 AC5).
- **Errors:**
  | Status | code | Condition |
  |---|---|---|
  | 404 | `NOT_FOUND` | claim id does not exist |
  | 409 | `INVALID_STATE_TRANSITION` | claim is not currently `MANUAL_REVIEW` |
  | 422 | `VALIDATION_ERROR` | missing/invalid `outcome` or `reason_code` |
- **Rate limits:** N/A.

---

## Admin API (E9-S4) — Admin role

All routes below require `require_role(ADMIN)`; any other role (including `ASSESSOR`) receives
`403 FORBIDDEN` (E9-S4 AC4).

### `GET /api/admin/claims`

- **Purpose:** claim queue filtered by status/product (E11-S4).
- **Query params:** `status` (optional, `ClaimStatus`), `product` (optional, `ClaimType`).
- **Response `200 OK`:**
  ```json
  { "claims": [ { "claim_id": 42, "claim_type": "MOTOR", "status": "MANUAL_REVIEW",
      "claim_amount": "75000.00", "updated_at": "2026-03-11T09:04:00Z" } ] }
  ```
- **Errors:** none beyond standard auth statuses.
- **Rate limits:** N/A.

### `GET /api/admin/payouts`

- **Purpose:** immutable payout audit trail — every `Settlement` row, reverse-chronological
  (E9-S4 AC2, E11-S4 AC2).
- **Query params:** none.
- **Response `200 OK`:**
  ```json
  { "payouts": [ { "settlement_id": 9, "claim_id": 42, "payout_amount": "35000.00",
      "payment_reference": "STUB-PAY-0000042-01", "created_at": "2026-03-11T09:05:00Z" } ] }
  ```
  Ordered by `created_at` descending.
- **Errors:** none beyond standard auth statuses.
- **Rate limits:** N/A.

### `POST /api/admin/claims/{id}/override`

- **Purpose:** force a claim decision/status with a mandatory reason code, recorded as an
  auditable `AdminOverride` event (E8-S2, AC-09).
- **Path params:** `id` — claim id.
- **Request body:**
  ```json
  { "command": "FORCE_APPROVE", "reason_code": "Manual goodwill approval after phone review" }
  ```
  | Field | Type | Required | Notes |
  |---|---|---|---|
  | `command` | `AdminOverrideCommand` | yes | `FORCE_APPROVE｜FORCE_REJECT｜FORCE_MANUAL_REVIEW｜FORCE_RETRY` |
  | `reason_code` | string | yes, min length 1 | free-text audit reason (E8-S2 AC2) |
- **Response `200 OK`:**
  ```json
  { "claim_id": 42, "override_id": 5, "claim_status": "AUTO_APPROVED" }
  ```
- **Errors:**
  | Status | code | Condition |
  |---|---|---|
  | 404 | `NOT_FOUND` | claim id does not exist |
  | 422 | `VALIDATION_ERROR` | `reason_code` missing/empty (E8-S2 AC2) |
  | 409 | `INVALID_STATE_TRANSITION` | requested command has no valid transition from the claim's current (possibly now-stale) status — this is also how concurrent double-override races are rejected (E8-S2 AC4) |
- **Rate limits:** N/A.

### `GET /api/admin/claims/{id}/overrides`

- **Purpose:** per-claim override audit history (E9-S4 AC3, E11-S4 AC4).
- **Path params:** `id` — claim id.
- **Response `200 OK`:**
  ```json
  { "overrides": [ { "override_id": 5, "admin_actor_id": "admin-1", "command": "FORCE_APPROVE",
      "reason_code": "Manual goodwill approval after phone review",
      "created_at": "2026-04-05T14:00:00Z" } ] }
  ```
  Ordered by `created_at` ascending (matches `list_admin_overrides()`, E3-S4 AC4).
- **Errors:**
  | Status | code | Condition |
  |---|---|---|
  | 404 | `NOT_FOUND` | claim id does not exist |
- **Rate limits:** N/A.

### `POST /api/admin/claims/{id}/retry`

- **Purpose:** resume a claim stuck in `PROCESSING_FAILED` (E6-S3 AC4). Not enumerated as a
  distinct story in E9-S4's description, but required to give `retry_pipeline()` an API entry
  point — documented here as a direct, minimal extension of the admin API surface (grouped with
  E9-S4 since it shares `require_role(ADMIN)` and the admin router).
- **Path params:** `id` — claim id (must currently be `PROCESSING_FAILED`).
- **Request body:** none.
- **Response `200 OK`:**
  ```json
  { "claim_id": 42, "claim_status": "FRAUD_SCREENING" }
  ```
  `claim_status` reflects the state the pipeline resumed into.
- **Errors:**
  | Status | code | Condition |
  |---|---|---|
  | 404 | `NOT_FOUND` | claim id does not exist |
  | 409 | `INVALID_STATE_TRANSITION` | claim is not currently `PROCESSING_FAILED` |
- **Rate limits:** N/A.

---

## Endpoint-to-story cross-reference

| Endpoint | Story |
|---|---|
| `GET /health` | Infra / NFR-07 (not tied to a single story) |
| `POST /api/claims` | E9-S1 |
| `GET /api/claims/{id}` | E9-S1 |
| `POST /api/claims/{id}/reopen` | E9-S1 |
| `GET /api/claims/documents/pending` | E9-S2 |
| `PATCH /api/claims/{id}/documents/{type}` | E9-S2 |
| `GET /api/claims/fraud-alerts` | E9-S3 |
| `GET /api/claims/{id}/workbench` | E9-S3 |
| `POST /api/claims/{id}/decision` | E9-S3 |
| `GET /api/admin/claims` | E9-S4 |
| `GET /api/admin/payouts` | E9-S4 |
| `POST /api/admin/claims/{id}/override` | E9-S4 |
| `GET /api/admin/claims/{id}/overrides` | E9-S4 |
| `POST /api/admin/claims/{id}/retry` | E9-S4 (extension, backs E6-S3 AC4) |
