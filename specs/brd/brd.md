# Business Requirements Document — ClaimFlow

**Business Case ID:** BC-AINE-005
**Domain:** Insurance — Claims Operations
**Status:** Draft — pending human approval
**Source documents:** `AI-Native_Engineer_Capstone_ClaimFlow.pdf` (BC-AINE-005 brief), existing Claude Harness Engine scaffold (`CLAUDE.md`, `design.md`, `project-manifest.json`)

---

## 1. Executive Summary

ClaimFlow is the FNOL-to-settlement claims processing platform for Horizon Insurance, covering
motor, health, and life products. It takes a claim from first notice of loss through document
verification, rule-based fraud screening, financial assessment, decision, settlement, and dispute
(reopen), with every state transition enforced and audited. The platform is built entirely by
Claude Code agents under the AI-Native Engineer Capstone's no-hand-coding constraint: the
deliverable is graded both on the functioning application (10 acceptance criteria across 3 claim
types) and on the evidence that the build was agent-led (specs, agents, skills, hooks, PR history).

The target outcome for this engagement is a **Merit-band submission (75–89/100)**: every mandatory
item in the rubric's section 8.1 is covered solidly across all three claim types, with the
Good-to-Have extras (multiple sprint cycles, bonus agents, knowledge-deposit log) picked up only if
they fall out naturally from the mandatory work — they are not separately scoped or scheduled.

## 2. Problem Statement

Horizon Insurance needs a single pipeline that takes a claim from intake to payout across three
distinct product lines (motor, health, life), each with different document requirements and payout
math, while enforcing:

- Policy validity at time of loss (no payouts against lapsed/inactive policies).
- Consistent document verification before a claim can be assessed.
- Deterministic, auditable fraud screening (not a black box).
- Financial correctness (payable amount is never negative, always computed in fixed-point decimal).
- An auditable decision trail (why a claim was approved, sent to review, or rejected).
- Immutable settlement records and an append-only history of every claim, fraud score, assessment,
  and payout.
- A controlled path to reopen a disputed, already-settled claim without destroying the original
  record.

Cost of not solving this: claims processing stays manual/ad hoc, decisions are not explainable
(no reason codes), fraud is not screened consistently, and there is no audit trail for regulators
or internal review.

## 3. Target Users

| Role | Description | Technical level | Context of use |
|------|-------------|------------------|-----------------|
| Customer / Claimant | Policyholder filing a claim | Non-technical | Files FNOL, tracks status, disputes a settled claim; mobile/desktop web |
| Assessor | Internal claims handler | Domain-expert, non-technical | Reviews claim + fraud flags + assessed amount, submits a decision; desktop |
| Admin | Internal supervisor | Domain-expert, non-technical | Monitors queues (status/product/fraud/payout), overrides decisions with a reason code; desktop |

There is no separate "developer/API consumer" persona in scope — the platform is a first-party
web application for these three roles only.

## 4. Success Metrics

Since this is a capstone graded by automated rubric review rather than a live product, success is
measured against the rubric (21 parameters / 100 marks / 5 categories) rather than business KPIs:

- **Primary metric:** submission scores in the **Merit band (75–89/100)**.
- All 8.1 "Mandatory" deliverables present and functioning (working app, `docs/business-case.md`,
  spec files, AC-linked specs, agent substrate, harness integration with ≥3 PR-driven merges,
  `.mcp.json` with Playwright active).
- All 10 functional ACs (AC-01..AC-10) implemented for all 3 claim types, each with at least one
  test whose name/tag references its AC-N identifier.
- All 8 NFRs (NFR-01..NFR-08) satisfied and independently verifiable (e.g. NFR-08 via automated
  architecture tests, not manual inspection).
- ≥20 unit tests with a coverage artifact; ≥3000 lines of generated code; ≥3 architecture structural
  tests; CI pipeline green with Claude Code Action wired in.
- Zero direct commits to `main` — 100% of merges are PR-driven (≥3, ideally every merge).

"Users are happy" is explicitly not a metric here — there are no live users; the grader is the
metric.

## 5. Scope

### In Scope

- FNOL intake for motor, health, and life claims (AC-01).
- Policy-active validation at incident date, with `PolicyNotActiveException` on failure (AC-02).
- Per-claim-type document checklist enforcement: motor (police FIR + invoice), health (hospital
  bill + discharge summary), life (death certificate) (AC-03). **Checklist only** — see Alternatives,
  no file-upload widget.
- Deterministic rule-based fraud screening with a configurable threshold (AC-04).
- Assessment: `payable_amount = min(claim_amount, sum_insured) − deductibles − co_pay`, invariant
  `payable_amount ≥ 0` (AC-05).
- Decision engine: `AUTO_APPROVE` / `MANUAL_REVIEW` / `REJECT` with reason codes (AC-06).
- Settlement: immutable payout record linked to the claim, stubbed payment trigger (AC-07).
- Reopen/dispute: creates a new sub-claim linked to the original, original moves to `REOPENED`
  (AC-08).
- Admin override: command + reason code, recorded as an auditable override event (AC-09).
- Claim state-machine enforcement: invalid transitions raise `InvalidClaimStateException` (AC-10).
- Customer portal: file FNOL, track status/decision/reason codes/outstanding documents, dispute a
  settled claim.
- Internal portal: document verification queue, fraud alert queue, assessor workbench, admin
  dashboard (queue by status/product, fraud alerts, payout audit trail).
- Stubbed role-based access (Customer/Assessor/Admin) enforced at the controller layer.
- Full AI-native engineering substrate: project-specific specs, layered CLAUDE.md/AGENTS.md, ≥3
  skills, ≥2 commands, ≥2 hooks, ≥3 agents, ≥6 policy statements in `claude.rules/`, architecture
  tests, `docs/business-case.md`, `docs/architecture.md`, `docs/tdd.md`.

### Out of Scope

- Real payment orchestration or real payment rails (stub only, per capstone brief).
- Real ML-based fraud detection (rule-based, deterministic stub only).
- Real file storage/upload for supporting documents (checklist toggle only — see Alternatives).
- Real authentication/identity provider (stubbed role selector only — see Alternatives).
- Multi-tenant support, internationalization, or non-English locales.
- Formal WCAG accessibility audit (basic semantic HTML/keyboard nav only).
- Docker/cloud deployment (local dev servers only, per existing `project-manifest.json`).
- Good-to-Have extras (multiple sprint cycles per claim type, bonus agents beyond the required
  count, a dedicated knowledge-deposit log) — not separately scoped for the Merit target; picked up
  opportunistically only if they emerge naturally from the mandatory work.

## 6. MVP Definition

Unlike a typical product BRD, there is no smaller "first slice" than the full pipeline: the
capstone brief requires adjudication/settlement workflows for **at least 3 claim types** in the
first (and only planned) version. The MVP is therefore:

- All 10 ACs implemented end-to-end for all 3 claim types (motor, health, life) in a single
  pipeline, not phased in.
- The 3-role stubbed access model (Customer/Assessor/Admin), not a full identity system.
- Checklist-only document verification, not real file upload/storage.
- Minimal/utilitarian UI — functionality over visual polish, since the rubric explicitly excludes
  UI visual polish from evaluation.
- One responsive layout (customer portal); the internal assessor/admin portal is desktop-oriented
  only.

Anything beyond this (extra claim types, real auth, real file storage, multiple sprint cycles) is
explicitly deferred as a Good-to-Have, not part of the committed scope.

## 7. Alternatives Considered

### 7.1 Authentication / Role Enforcement — CHOSEN: Stubbed role selector

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A. Full JWT auth | Signup/login, hashed passwords, seeded demo users | Realistic | Adds real build hours to a 20-hour budget for something not evaluated on realism |
| **B. Stubbed role selector (chosen)** | Customer/Assessor/Admin dropdown, no password; `X-Role` + actor id enforced by a FastAPI dependency at the controller layer | Satisfies NFR-04 ("boundary enforced at controller layer") literally; minimal build cost; frees hours for AC coverage and tests | Not a realistic identity model |
| C. Lightweight session auth | Login form, plaintext-matched seeded users, no JWT | Middle ground | Still more build time than B for no rubric benefit |

**Rationale:** NFR-04 requires only that the auth *boundary* is enforced at the controller layer,
not a real identity provider. The rubric does not reward auth realism. Option B is the fastest path
that still satisfies the NFR and produces a real, testable authorization boundary.

### 7.2 Document Handling (AC-01, AC-03) — CHOSEN: Checklist only, no upload widget

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A. Real file-upload widget | Stores a stub reference (filename/hash), no real storage backend | Slightly more "real" UX | Extra frontend + backend surface for something explicitly marked "stubbed" in the brief |
| **B. Checklist only (chosen)** | Per-claim-type checklist with VERIFIED/MISSING toggles, no upload UI | Matches "stubbed upload" literally; simplest to build and test; AC-03's real requirement is checklist *enforcement*, not upload UX | None material for this scope |

**Rationale:** AC-01 says "supporting documents (stubbed upload)" and AC-03 is about checklist
*enforcement varying by claim type* — the enforcement logic is what's graded, not an upload
experience.

### 7.3 Fraud Screening Engine (AC-04) — CHOSEN: Declarative rule set

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A. Hardcoded if/else | Threshold checks embedded in service code | Fastest to write | Not configurable, harder to unit-test each rule independently |
| **B. Declarative JSON-config rule set (chosen)** | Named rules (ratio checks, claim-frequency checks, missing-doc signals) with point weights, summed and compared to a configured threshold loaded from config | Deterministic (required by AC-04); each rule independently unit-testable; threshold tunable without code changes | Slightly more up-front structure than A |
| C. Pluggable rule-interface with runtime-registered rule classes | Full strategy pattern | Most extensible, best architecture-discipline story | Over-engineered for a 20-hour, rule-based-stub-only scope |

**Rationale:** AC-04 explicitly requires a deterministic score and a configurable threshold; a
declarative rule set makes both properties visible and testable without the overhead of a full
plugin architecture.

### 7.4 Claim State Machine (AC-10, NFR-08) — CHOSEN: Explicit transition-table module

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A. Status enum + scattered guards | Each service method checks/sets `claim.status` inline | Fastest initially | Guards drift out of sync across methods; hard to prove NFR-08 ("architecture rules enforced as automated tests") |
| **B. Explicit state-machine module (chosen)** | Single `transition(claim, event)` gate backed by a `{FROM_STATE: {EVENT: TO_STATE}}` table; all status changes must go through it; raises `InvalidClaimStateException` on an invalid entry | Directly satisfies AC-10; the transition table itself is a natural target for an architecture/structural test ("no service method sets `claim.status` directly") | Slightly more design work up front |

**Rationale:** Centralizing transitions is the only approach that lets a structural test
mechanically verify "no direct status mutation," which is exactly what NFR-08 asks for.

### 7.5 Database Migrations (NFR-05) — CHOSEN: Hand-rolled numbered SQL scripts

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A. Alembic | Real migration framework, autogeneration, diagram-friendly | More "enterprise" | Adds a dependency and setup/learning overhead not needed for a single SQLite file in a 20-hour build |
| **B. Numbered SQL scripts (chosen)** | `migrations/0001_*.sql`, `0002_*.sql`, ... applied in order at startup, never edited after being applied | Simple, transparent, still satisfies "append-only migrations" literally | No autogeneration; scripts are hand-written per schema change |

**Rationale:** SQLite + a fixed, small schema does not need Alembic's autogeneration or multi-DB
abstraction; the append-only property is trivially satisfied by "never edit an already-applied
script, only add new ones."

### 7.6 UI Investment — CHOSEN: Minimal/utilitarian, customer portal responsive only

Per `calibration-profile.json`, the design-scoring weights are already set to functionality-heavy
(`functionality: 1.5` vs `design_quality: 0.75`) because the capstone rubric explicitly excludes
visual polish from evaluation. Confirmed direction: plain component styling (no custom design
system), one responsive layout on the customer portal (the more plausible mobile use case), and the
assessor/admin portal built desktop-only. No formal WCAG audit — basic semantic HTML and keyboard
navigation only.

## 8. Technical Architecture

- **Backend:** Python 3.12, FastAPI, `pip` for dependencies, `ruff` (lint), `mypy` (types),
  `pytest` (tests).
- **Frontend:** TypeScript, React, Vite, `npm`, `eslint`, `tsc`, `vitest` (unit), Playwright (E2E).
- **Database:** SQLite, single local file, hand-rolled numbered append-only migration scripts
  (§7.5).
- **Layered architecture:** strict one-way dependency chain — Types → Config → Repository →
  Service → API → UI (per `.claude/architecture.md`); enforced by structural tests (NFR-08) and the
  `check-architecture` hook.
- **Auth boundary:** stubbed role selector, FastAPI dependency injected at the controller layer
  (§7.1); no external identity provider.
- **Fraud engine:** declarative JSON-config rule set, loaded by the service layer, deterministic
  output (§7.3).
- **State machine:** centralized `transition()` gate module (§7.4).
- **Deployment:** local only — `init.sh` installs dependencies and starts backend (`:8000`,
  uvicorn) and frontend (`:5173`, Vite dev server); no Docker/cloud target.
- **CI:** `.gitlab-ci.yml`, lint + test stages for backend and frontend, Claude Code Action wired
  into the workflow (rubric §7.5), PR-only merges to `main` (≥3 required).
- **MCP:** `.mcp.json` declares the Playwright MCP server for `evaluator`/`design-critic` agents.

Performance/scale requirements are minimal by design: this is a local single-user-at-a-time
capstone demo, not a production multi-tenant service. The only hard performance NFR is NFR-07
(health endpoint returns 200 within 1 second of successful startup).

## 9. Data Model Overview

Core entities (final field-level schema to be produced in `/spec` and `/design`):

| Entity | Notes |
|--------|-------|
| `Policy` | Policy number, product type (motor/health/life), status (ACTIVE/LAPSED/...), sum_insured, effective/expiry dates |
| `Claim` | Policy ref, claim_type, incident_date, claim_amount, status (via state machine), `parent_claim_id` (nullable, set when created via reopen — AC-08) |
| `ClaimDocument` | Claim ref, document_type (per claim-type checklist), verification_status (VERIFIED/MISSING) |
| `FraudScreening` | Claim ref, computed score, rule breakdown, flagged boolean, threshold used at time of screening — append-only (NFR-02) |
| `Assessment` | Claim ref, claim_amount, sum_insured snapshot, deductible, co_pay, payable_amount (Decimal, NFR-01) — append-only |
| `Decision` | Claim ref, outcome (AUTO_APPROVE/MANUAL_REVIEW/REJECT), reason codes, decided_by (assessor/system) — append-only |
| `Settlement` | Claim ref, payout amount, immutable payout record (AC-07) — append-only |
| `ClaimStateTransition` | Claim ref, from_state, to_state, event, timestamp — audit trail backing AC-10 |
| `AdminOverride` | Claim ref, admin actor, command, reason code, timestamp — audit trail backing AC-09 |

`Claim.reopen()` never mutates the original claim's terminal record; it inserts a new `Claim` row
with `parent_claim_id` set and moves the original to `REOPENED` via the state machine (§7.4),
consistent with the append-only requirement (NFR-02).

## 10. External Integrations

None required. Per the capstone brief's Out-of-Scope section: no real payment orchestration, no
real payment rails, no real ML fraud-detection service. All "external" touchpoints (payment
disbursement, document storage) are stubbed within the application boundary. The only external
tool integration is the Playwright MCP server used by internal evaluation/design-critic agents
(development-time only, not a runtime dependency of the application).

## 11. Edge Cases & Constraints

### Synthetic business rules (invented for this build, clearly not real actuarial figures)

> These are placeholder values chosen to make AC-04/AC-05 concretely testable. They are
> configuration, not hardcoded logic, and can be changed without a spec rewrite.

**Fraud scoring rules (sum of triggered rule weights; flag if total ≥ 60):**
| Rule | Weight |
|------|--------|
| `claim_amount / sum_insured` ratio > 0.8 | +40 |
| Claim filed within 3 days of policy inception | +25 |
| More than 2 claims on the same policy within a trailing 90-day window | +30 |
| Motor claim missing the police FIR document | +15 |
| Claim amount is a round number divisible by 10,000 | +10 |

**Deductible / co-pay by claim type:**
| Claim type | Deductible | Co-pay |
|------------|-----------|--------|
| Motor | Flat 5,000 | None |
| Health | Flat 1,000 | 10% of (claim_amount − deductible) |
| Life | None | None |

**Decision thresholds:**
- `payable_amount == 0` → `REJECT`, reason code `ZERO_PAYABLE_AMOUNT`.
- Fraud-flagged → `MANUAL_REVIEW`, reason code `FRAUD_FLAG`.
- Documents not fully `VERIFIED` → claim held at `DOCS_PENDING`, does not proceed to fraud
  screening/assessment.
- Not flagged, documents complete, `payable_amount` ≤ synthetic auto-approve ceiling (50,000) →
  `AUTO_APPROVE`, reason code `AUTO_APPROVED_LOW_RISK`.
- Not flagged, `payable_amount` > ceiling → `MANUAL_REVIEW`, reason code `HIGH_VALUE_REVIEW`.
- Policy not `ACTIVE` at incident date → immediate `REJECT` with `PolicyNotActiveException`
  (AC-02), reason code `POLICY_INACTIVE`, before any downstream processing.

### Failure handling

- Duplicate FNOL for the same policy + incident date: **rejected at intake** with a
  `DuplicateClaimException`-style 409 response rather than silently creating a second claim —
  prevents accidental double-filing while still allowing legitimate multiple claims on distinct
  incident dates.
- If fraud screening or assessment raises an unexpected error mid-pipeline, the claim moves to a
  `PROCESSING_FAILED` state (visible to admin, not silently 500'd to the customer) with the error
  logged (structured JSON, NFR-06, no PII) and an admin can retry or manually route the claim.
- Concurrent admin overrides on the same claim: the state-machine gate (§7.4) makes the second,
  now-stale transition fail with `InvalidClaimStateException` rather than silently double-applying.

### Operational constraints

- No uptime SLA (local dev demo, not a hosted service).
- No formal rate limits (single-operator usage during grading/demo).
- No compliance regime targeted explicitly, but NFR-03 (no PII in logs) is treated as a hard
  constraint: claim narratives, document content, and health-related data are never written to
  logs, mirroring real insurance-domain PII handling even though this is synthetic data only
  (per the capstone's Synthetic-Data Rule).
- Most likely failure modes in the first 6 months (framed for the capstone's evaluation window):
  schema drift between spec and code (mitigated by the Spec-Is-Truth Rule), architecture-rule
  regressions from agent-generated code (mitigated by the `check-architecture` hook and structural
  tests), and coverage regressions (mitigated by the coverage-baseline gate).

## 12. UI Context

- **Customer portal** (responsive: desktop/tablet/mobile): FNOL form (policy number, incident
  date, claim type, document checklist), claim tracker (status, decision, reason codes, missing
  documents), dispute action on a `SETTLED` claim.
- **Internal portal** (desktop-oriented only): document verification queue (per-claim-type
  checklist, VERIFIED/MISSING toggles), fraud alert queue, assessor workbench (claim detail, fraud
  flags, assessed amount, decision rationale, submit decision), admin dashboard (claim queue by
  status/product, fraud alert queue, payout audit trail, override action with reason code).
- **Design references:** none supplied; no brand guidelines — utilitarian styling using a plain
  component approach, consistent with the low `design_quality`/`originality`/`craft` weighting in
  `calibration-profile.json`.
- **Devices/viewports:** customer portal responsive across mobile/tablet/desktop; internal portal
  desktop-only (typical for back-office tooling).
- **Accessibility:** basic semantic HTML and keyboard navigability; no formal WCAG-level audit
  performed (not required by the brief).

## 13. Open Questions

None blocking — all prior open questions were resolved by the human's answers above (grade-band
target, auth/role approach, document-upload approach, fraud/state-machine/migration/UI
alternatives). Items intentionally deferred to `/spec` rather than decided here:

- Exact field-level schema for each entity in §9 (types, nullability, indexes).
- Exact wording of all reason codes and Given-When-Then acceptance criteria per AC (rubric §7.2
  requires GWT format — to be produced in `/spec`).
- Exact list of the ≥6 `claude.rules/` policy statements (candidates: no-hand-coding, spec-is-truth,
  PR-only-merge, synthetic-data-only, append-only-records, no-PII-in-logs, fixed-point-money-math,
  one-way-architecture — final selection in `/spec`).
- Names/responsibilities of the ≥3 project-specific agents, ≥3 skills, ≥2 commands, ≥2 hooks beyond
  the harness's 7 base agents (to be scoped in `/spec`/`/design`).
