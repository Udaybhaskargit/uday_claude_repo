# Dependency Graph — ClaimFlow

Stories are organized into 11 dependency groups (A..K). Stories within the same group have no dependencies on each other and can be built/executed in parallel. Each group depends only on stories in earlier groups.

## Group A

| Story ID | Title | Layer | Depends On |
|----------|-------|-------|------------|
| E1-S1 | Define core domain types and enums | Types | (none) |
| E1-S2 | Build the claim state machine transition gate | Types | (none) |
| E1-S3 | Define reason codes and domain exceptions | Types | (none) |

## Group B

| Story ID | Title | Layer | Depends On |
|----------|-------|-------|------------|
| E2-S1 | Load fraud rule configuration from declarative config | Config | E1-S1 |
| E2-S2 | Load deductible, co-pay, and decision threshold configuration | Config | E1-S1 |
| E2-S3 | Centralize application and role configuration | Config | E1-S1 |

## Group C

| Story ID | Title | Layer | Depends On |
|----------|-------|-------|------------|
| E3-S1 | Write append-only numbered SQLite migrations | Repository | E2-S3 |
| E8-S1 | Implement the stubbed role-based auth dependency | API | E1-S1, E2-S3 |

## Group D

| Story ID | Title | Layer | Depends On |
|----------|-------|-------|------------|
| E3-S2 | Build the policy repository | Repository | E3-S1 |
| E3-S3 | Build the claim repository | Repository | E3-S1, E1-S2 |
| E3-S4 | Build the append-only audit repositories | Repository | E3-S1 |

## Group E

| Story ID | Title | Layer | Depends On |
|----------|-------|-------|------------|
| E4-S1 | Implement the FNOL intake service | Service | E3-S3 |
| E5-S2 | Implement the deterministic fraud scoring engine | Service | E2-S1, E3-S3 |
| E6-S1 | Implement the assessment service | Service | E3-S3, E3-S2, E2-S2 |
| E7-S2 | Implement the reopen/dispute service | Service | E3-S3, E1-S2 |
| E8-S2 | Implement the admin override service | Service | E3-S3, E1-S2, E8-S1 |

## Group F

| Story ID | Title | Layer | Depends On |
|----------|-------|-------|------------|
| E4-S2 | Enforce policy-active validation at incident date | Service | E4-S1, E3-S2 |
| E4-S3 | Detect and reject duplicate FNOL submissions | Service | E4-S1, E3-S3 |
| E5-S1 | Enforce the per-claim-type document checklist | Service | E4-S1 |
| E5-S3 | Persist fraud screenings and gate the pipeline | Service | E5-S2, E3-S4 |
| E9-S4 | Expose the admin API for queues, overrides, and audit trail | API | E8-S2 |

## Group G

| Story ID | Title | Layer | Depends On |
|----------|-------|-------|------------|
| E11-S4 | Build the admin dashboard UI | UI | E9-S4 |
| E6-S2 | Implement the decision engine | Service | E6-S1, E5-S3 |
| E9-S2 | Expose the document verification API | API | E5-S1, E8-S1 |

## Group H

| Story ID | Title | Layer | Depends On |
|----------|-------|-------|------------|
| E11-S1 | Build the document verification queue UI | UI | E9-S2 |
| E6-S3 | Orchestrate the claim pipeline with failure handling | Service | E6-S2, E5-S1 |
| E9-S3 | Expose the assessor workbench API | API | E5-S3, E6-S2, E8-S1 |

## Group I

| Story ID | Title | Layer | Depends On |
|----------|-------|-------|------------|
| E11-S2 | Build the fraud alert queue UI | UI | E9-S3 |
| E7-S1 | Implement the settlement service | Service | E6-S3, E3-S4 |
| E9-S1 | Expose the claims API for intake, tracking, and dispute | API | E4-S3, E6-S3, E7-S2 |

## Group J

| Story ID | Title | Layer | Depends On |
|----------|-------|-------|------------|
| E10-S1 | Build the FNOL submission form | UI | E9-S1 |
| E10-S2 | Build the claim tracker view | UI | E9-S1 |
| E11-S3 | Build the assessor workbench UI | UI | E11-S2 |

## Group K

| Story ID | Title | Layer | Depends On |
|----------|-------|-------|------------|
| E10-S3 | Build the dispute action flow | UI | E10-S2 |

## Validation

- No circular dependencies (validated by topological sort at generation time).
- Every story's dependencies resolve to an earlier group letter.
- Foundation layers (Types, Config, Repository) occupy groups A-D; Service/API occupy the middle groups; UI occupies the final groups (J, K).
