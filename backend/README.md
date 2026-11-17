# MongoDB transaction setup

Application writes and portfolio deletion require MongoDB transactions. Use a replica set (or MongoDB Atlas); standalone MongoDB is not safe for these mutations. Unsupported transactional mutations return HTTP 503 and do not fall back to non-transactional writes. With seeding enabled, startup fails if the server rejects seed transactions rather than serving an incomplete inventory. With seeding disabled, existing records may be read, but transactional mutations still fail closed.

For local development, create an isolated data directory and initialize a single-node replica set (do not use an existing database path):

```sh
mkdir -p "$HOME/etsip-mongo/data"
mongod --replSet rs0 --port 27119 --bind_ip 127.0.0.1 --dbpath "$HOME/etsip-mongo/data" --logpath "$HOME/etsip-mongo/mongod.log" --fork
mongosh 'mongodb://127.0.0.1:27119/?directConnection=true' --eval 'rs.initiate({_id:"rs0",members:[{_id:0,host:"127.0.0.1:27119"}]})'
```

Wait for a primary election. Copy `.env.example` to `.env`, set a randomly generated JWT secret and appropriate demo passwords, and use `MONGODB_URI=mongodb://127.0.0.1:27119/?replicaSet=rs0`. Database name remains separately configured. Tests use that replica set by default; `TEST_MONGODB_URI` selects another transaction-capable test server. Each test uses and deletes only its own uniquely named test database. The server must be started before running pytest.

Compose starts a single replica-set member advertised as `db:27017`; its health check initializes the replica set and waits for primary before starting the backend. The Compose volume persists data. A previously initialized replica-set volume with a different advertised hostname requires an appropriate migration or a fresh volume; do not delete a volume containing needed data.

## Isolated Playwright E2E (after critic approval)

The E2E specs use explicitly provisioned test environment variables, not Vite `loadEnv` on the backend directory. Keep `backend/.env` out of the test setup.

Use a **dedicated, private local MongoDB replica-set process and new empty data directory**, never a shared development, production, or forwarded database. The commands below assume a Unix shell, MongoDB tools on PATH, free ports 27119, 8000 and 5173, backend dependencies installed in a Python virtual environment, and frontend dependencies installed. Replace the Python path with the absolute executable of that environment; it must have the backend requirements, including PyMongo and Uvicorn. Do not use production credentials. The backend is started from `frontend/` rather than `backend/`, so it does not load `backend/.env`.

**Required operator guarantee:** the dedicated process and its data directory are exclusively for this invocation, and no other client or runner can connect to or write to it from before reservation until all test processes have stopped. Use an isolated sandbox or equivalent access controls that ensure this, not merely a loopback bind; stop if this guarantee cannot be made. MongoDB cannot atomically reserve an entire database against uncooperative clients. The checks below detect existing or intervening collections before seeding, but cannot prevent a client writing after the final check. Set `E2E_EXCLUSIVE_MONGO_RUN_ID` only when this guarantee holds; the acknowledgment is not technical proof of isolation.

From the repository root, create a **new** directory and start an isolated replica set (if the directory already exists, stop and choose another; do not reuse it):

```sh
set -eu
export E2E_MONGO_DIR="$HOME/etsip-e2e-mongo-$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
mkdir "$E2E_MONGO_DIR"
mkdir "$E2E_MONGO_DIR/data"
mongod --replSet rs0 --port 27119 --bind_ip 127.0.0.1 --dbpath "$E2E_MONGO_DIR/data" --logpath "$E2E_MONGO_DIR/mongod.log" --fork
mongosh 'mongodb://127.0.0.1:27119/?directConnection=true' --eval 'rs.initiate({_id:"rs0",members:[{_id:0,host:"127.0.0.1:27119"}]})'
```

Wait for this member to become PRIMARY. Then, in the same shell, set an absolute `E2E_PYTHON` path and generate a fresh ID and four distinct, random, test-only secrets for **each** invocation. For example (replace `/absolute/path/to/venv/bin/python`):

```sh
export E2E_PYTHON=/absolute/path/to/venv/bin/python
export E2E_MONGODB_URI='mongodb://127.0.0.1:27119/?replicaSet=rs0'
export E2E_RUN_ID="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
export E2E_EXCLUSIVE_MONGO_RUN_ID="$E2E_RUN_ID"
export E2E_JWT_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export E2E_SEED_ADMIN_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export E2E_ADMIN_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export E2E_DEMO_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
node frontend/node_modules/@playwright/test/cli.js test --config frontend/playwright.config.ts
```

The setup passes that demo password to `E2E_PASSWORD`, `E2E_EXECUTIVE_PASSWORD`, `E2E_READONLY_PASSWORD`, `E2E_AUDITOR_PASSWORD` and `SEED_DEMO_PASSWORD`; the seed administrator password is distinct from the rotated business administrator password. Do not log or publish these values. Playwright rejects non-loopback Mongo and existing web servers, requires the explicit ownership acknowledgment, refuses a pre-existing database, atomically creates a reservation collection to arbitrate competing same-ID runners, and verifies that it is the only collection with exactly the expected marker before startup seeding. It never automatically drops data; a failed reservation may leave a marker behind. Keep the run ID and directory path for recovery; reruns require a new ID and new secrets. A hard interruption may leave disposable `e2e-*` and `journey-*` users active; inspect/deactivate them only in the confirmed-owned run database. Once finished, stop **only this dedicated mongod**, verify its process and data directory identity, then manually remove that dedicated directory if no longer needed. Never drop or delete a database or directory whose ownership is uncertain. Browser traces/screenshots and this test data may contain sensitive test material; handle and remove them appropriately.
