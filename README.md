# KP ETSIP Release 1

A self-contained quality inventory and executive insight application. The React/Vite/TypeScript frontend calls the FastAPI REST API, which persists roles, users, portfolios, applications and audit events in MongoDB using native async PyMongo. Scores and defects are manually maintained inventory values, not automated evidence.

## Run locally

Requirements: Node.js 22, Python 3.12, and MongoDB 8 configured as a replica set. Application writes, audit consistency and portfolio deletion require transactions; standalone MongoDB cannot safely support them. See [backend/README.md](backend/README.md) for a single-node replica set and isolated test setup.

1. Copy `backend/.env.example` to `backend/.env` and set a fresh, strong JWT secret and distinct seed passwords. Copy `frontend/.env.example` to `frontend/.env`; adjust proxy/CORS as needed. Never commit either `.env` file. Example values are placeholders, not production credentials.
2. Start a MongoDB replica set and set `MONGODB_URI` and `MONGODB_DB` in backend configuration. Keep database credentials and the signing secret private; use HTTPS at the load balancer in deployed environments.
3. Install backend dependencies in a virtual environment with `pip install -r backend/requirements.txt`, then from `backend/` run `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
4. From `frontend/`, run `npm ci` and `npm run dev`. The Vite development proxy forwards `/api` to the configured backend. To build, run `npm run build`.
5. Alternatively, after setting `backend/.env`, run `docker compose up --build -d`. Compose initializes MongoDB rs0 and starts the backend and frontend; `FRONTEND_PORT` controls the published frontend port (default 8080). Never remove a volume containing data you need.

The initial Administrator is `admin@ketsip.local` with the configured `SEED_ADMIN_PASSWORD`; first sign-in requires a password change. The five other demo accounts are `executive@ketsip.local`, `leader@ketsip.local`, `engineer@ketsip.local`, `auditor@ketsip.local`, and `readonly@ketsip.local`, using the configured `SEED_DEMO_PASSWORD`. Set strong non-default values before first startup and rotate all demo credentials before exposure. Seed inserts are idempotent and do not reset changed passwords or records. Seed data consists of six roles/users, three portfolios and ten applications.

## Access and behavior

Local email/password sign-in issues an eight-hour bearer JWT; logout, password and sensitive account changes revoke prior tokens. Permissions are checked server-side against live account/role state and portfolio scope. Administrator alone manages users/roles and deletes records; Auditor has separate read/export audit access. Empty scope means all portfolios only for Administrator, Executive and Auditor; other roles see none. Dashboard averages are half-up rounded and empty averages display N/A. Filtered dashboard portfolio totals include only portfolios with matching applications. Referenced portfolios cannot be deleted, and users are deactivated rather than physically deleted.

The API is rooted at `/api`; business routes require bearer authentication except `POST /api/auth/login`, and `/api/health` provides process liveness. Application and portfolio reports support JSON pages and `format=csv`; audit CSV is available through `/api/audit-logs?format=csv`. CSV values are escaped against spreadsheet formulas. CSV reports page over live data and are not snapshot-isolated: concurrent edits during a long export can change rows. Restricted-scope auditors see only historical portfolio events whose scope can be established safely; unscoped historical application/user/login events are excluded rather than inferred. Exports are audited when streaming begins, so a disconnected client may not receive the complete file.

## Verification

Run backend tests against a dedicated test MongoDB replica set: from `backend/`, `PYTHONPATH=. python -m pytest -q`. The test suite creates unique test databases and deletes those it owns. From `frontend/`, `node node_modules/vitest/vitest.mjs run` runs component tests. See `backend/README.md` for safe isolated Playwright provisioning and explicit environment requirements. The browser setup must never use a shared or production MongoDB server.

The delivery verification record is in `test_report.yaml` in the pipeline workspace. Current dependencies report two moderate npm audit advisories; review them before production deployment. JWT bearer storage is client-accessible as required by the release contract, so deploy with a carefully reviewed CSP and HTTPS edge configuration. Production ingress must provide HTTPS, HSTS, CSP and framing restrictions; the application API itself supplies `X-Content-Type-Options` and no-store headers.
