# Deployment — ClaimFlow

**Reality check (per `project-manifest.json` `"deployment": {"method": "local"}` and BRD §8/§11):**
this capstone has exactly one real deployment target — a developer/grader's local machine. There is
no container image, no cloud environment, and no deploy stage in CI. Section 5 below is explicitly
a **forward-looking, not-yet-implemented** section; do not generate infrastructure that contradicts
the manifest.

---

## 1. Local Development Workflow (the only real environment)

### 1.1 Bootstrap

```bash
./init.sh
```

`init.sh` (repo root) is responsible for, in order:

1. Installing backend dependencies: `cd backend && pip install -r requirements.txt`.
2. Applying database migrations by starting the backend once (the migration runner in
   `backend/src/db/migration_runner.py` applies any unapplied `backend/migrations/*.sql` file at
   app startup — see E3-S1).
3. Installing frontend dependencies: `cd frontend && npm ci` (or `npm install` on first run).
4. Starting the backend: `uvicorn src.main:app --reload --port 8000` (from `backend/`).
5. Starting the frontend: `npm run dev -- --port 5173` (from `frontend/`).

Resulting local topology:

| Service | URL | Notes |
|---|---|---|
| Backend (FastAPI/uvicorn) | `http://localhost:8000` | `GET /health` returns `{"status": "ok"}` within 1s of startup (NFR-07) |
| Frontend (Vite dev server) | `http://localhost:5173` | Talks to the backend directly; no reverse proxy |

### 1.2 Manual commands (if not using `init.sh`)

```bash
# Backend
cd backend
pip install -r requirements.txt
ruff check --fix .
mypy src/
pytest -x -q --cov=src

# Frontend
cd frontend
npm install
npm run lint
npm run typecheck
npm test
npx playwright test
```

### 1.3 Environment variables / secrets (local)

- All local configuration lives in a **`.env` file at the relevant app root** (`backend/.env`,
  `frontend/.env`), which is **never committed** (must be listed in `.gitignore`). A
  `.env.example` (committed, no real values) documents the expected keys:

  **`backend/.env.example`**
  ```
  CLAIMFLOW_DB_PATH=./claimflow.db
  CLAIMFLOW_BACKEND_PORT=8000
  CLAIMFLOW_FRONTEND_PORT=5173
  CLAIMFLOW_VALID_ROLES=CUSTOMER,ASSESSOR,ADMIN
  ```

  **`frontend/.env.example`**
  ```
  VITE_API_BASE_URL=http://localhost:8000
  ```

- `backend/src/config/app_config.py` (E2-S3) is the **only** module that reads these environment
  variables; every other layer receives `AppConfig` by dependency injection. A missing required
  variable with no default raises a typed config error at startup rather than silently defaulting
  (E2-S3 AC3).
- There are no real secrets in this system (no API keys, no payment credentials — the payment
  trigger is a stub per BRD §10/§7). `.env` exists for portability of ports/paths, not secret
  management. If a future integration ever introduces a real secret, it must go through `.env`
  (never hardcoded, never committed) and be added to `.env.example` as a placeholder-only key.

### 1.4 Database lifecycle (local)

- `backend/claimflow.db` is a single SQLite file, git-ignored, created on first backend startup by
  the migration runner.
- To reset local state: stop the backend, delete `backend/claimflow.db`, restart — migrations
  re-apply from `0001` in order.
- Migrations are **append-only**: once a numbered script has been applied, it is never edited
  (E3-S1 AC4 — a checksum mismatch on an already-applied migration raises a startup error). Schema
  changes are always a new `NNNN_description.sql` file.

---

## 2. CI Pipeline (GitLab CI — lint + test only, no deploy stage)

`.gitlab-ci.yml` defines two stages, each path-scoped so unrelated changes don't trigger the other
stack's pipeline:

| Stage | Job | Trigger | Commands |
|---|---|---|---|
| lint | `backend-lint` | `backend/**/*` changed | `pip install -r requirements.txt && ruff check . && mypy src/` |
| test | `backend-test` | `backend/**/*` changed | `pip install -r requirements.txt && pytest -x -q --cov=src --cov-report=term --cov-report=xml` (Cobertura report published as a CI artifact) |
| lint | `frontend-lint` | `frontend/**/*` changed | `npm ci && npm run lint && npm run typecheck` |
| test | `frontend-test` | `frontend/**/*` changed | `npm ci && npm test -- --run` |

There is deliberately **no `deploy` stage** — the pipeline's job is to gate merges (PR-only-merge
rule), not to ship anything. Playwright E2E tests run locally / in the evaluator agent's flow (see
`.mcp.json`), not as a blocking CI gate, since they require both servers running simultaneously.

### 2.1 Merge gating

- No direct commits to `main` (PR-only-merge rule, ≥3 PR-driven merges required per the capstone
  constraints in `CLAUDE.md`).
- A PR is mergeable only once its path-relevant lint + test jobs are green.
- Coverage floor: 80% (`project-manifest.json` `execution.coverage_threshold`), tracked via the
  Cobertura artifact from `backend-test`; there is no automatic CI gate enforcing this threshold
  today (`.gitlab-ci.yml` has no `coverage:` regex or quality-gate rule) — this is a documented
  **not-yet-implemented** enforcement gap the evaluator/review agents should flag if seen live at
  a lower percentage, rather than something to silently regenerate infrastructure for.

---

## 3. Rollback Procedure (local/PR-only reality)

Because there is no deploy stage and no live environment, "rollback" means reverting a merged
change on `main`, not rolling back a running service:

1. Identify the offending merge commit on `main` (via `git log` or the GitLab MR history).
2. Open a new branch: `git checkout -b fix/revert-<short-description>`.
3. Revert the commit(s): `git revert <commit-sha>` (never `git reset --hard` on `main` — that
   would rewrite shared history, which the PR-only-merge rule and general git safety practice both
   prohibit).
4. Push the branch and open a new PR, following the same lint+test gate as any other change.
5. If the offending change included a **migration** (`backend/migrations/NNNN_*.sql`), do **not**
   delete or edit that file (append-only rule, NFR-05) — add a new, later-numbered migration that
   undoes the schema change (e.g. `0010_drop_<table_or_column>.sql`), and revert the application
   code in the same PR.
6. Once merged, any developer/grader re-running `./init.sh` against a fresh `claimflow.db` gets the
   corrected schema/behavior automatically, since migrations are idempotent and applied in order
   (E3-S1 AC3).

---

## 4. Observability (local)

- Structured JSON logs are written to stdout by `backend/src/lib/logger.py`; no PII fields
  (claim narratives, document content, health data) are ever included (NFR-03/NFR-06).
- No external log aggregation, tracing, or metrics backend is configured — appropriate for a
  single-operator local demo. If this were to grow into the notional staging/prod environment in
  §5, that is where a real log sink would be introduced.

---

## 5. Forward-Looking: Notional Staging/Prod Guidance (NOT IMPLEMENTED)

**Everything in this section is aspirational documentation only.** None of it exists today; no
Dockerfile, no cloud config, and no deploy stage should be created to satisfy this section unless
a human explicitly re-scopes the project beyond the capstone's local-only requirement.

### 5.1 Promotion model (notional)

- `main` → auto-deployed to a `staging` environment on every merge (would require adding a
  `deploy-staging` stage to `.gitlab-ci.yml`, gated behind the existing lint+test stages).
- `staging` → promoted to `production` via a manually-triggered GitLab CI job after smoke tests
  pass against staging (health check + a scripted Playwright smoke suite).

### 5.2 Infrastructure (notional)

- Backend: containerized (`Dockerfile` based on `python:3.12-slim`), run behind a process
  manager/orchestrator (e.g. a single small container service — this app's scale does not justify
  Kubernetes).
- Frontend: static build (`npm run build`) served from a CDN/static host, calling the backend's
  public URL via `VITE_API_BASE_URL`.
- Database: SQLite is a **local-file** database and does not survive container
  restarts/horizontal scaling — a real staging/prod environment would need to swap in a real
  server-backed database (e.g. PostgreSQL) behind the same repository interfaces, which is exactly
  why the Repository layer is isolated behind interfaces in `backend/src/repositories/` (see
  `folder-structure.md`) rather than having services issue raw SQL directly.

### 5.3 Secrets handling (notional)

- Real secrets (a real payment-provider API key, if the payment stub were ever replaced) would be
  injected via the CI/CD platform's secret store (GitLab CI/CD variables, masked + protected), never
  committed, and never present in `.env.example` beyond a placeholder key name.

### 5.4 Rollback (notional)

- Same git-revert-and-PR mechanism as §3, plus an infrastructure-level rollback: re-point the
  `production` deploy job at the previous known-good build artifact/image tag rather than
  rebuilding from a reverted commit, to restore service faster while the revert PR goes through
  review.

### 5.5 Why this is deferred

Per BRD §5 (Out of Scope) and §8 (Technical Architecture), Docker/cloud deployment is explicitly
out of scope for the Merit-band capstone target — the rubric grades the working local application,
the specs, and the agent-led process, not production infrastructure maturity. This section exists
only so a future maintainer has a documented starting point if the project is ever extended beyond
the capstone.
