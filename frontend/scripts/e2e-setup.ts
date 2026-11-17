/** Prepare live E2E identities only in a freshly reserved, dedicated database. */
import { request, expect } from '@playwright/test';
import { execFile } from 'node:child_process';
import { accessSync, constants, statSync } from 'node:fs';
import { promisify } from 'node:util';
import path from 'node:path';

const configuredMongoUri = process.env.E2E_MONGODB_URI || '';
const runId = process.env.E2E_RUN_ID || '';
if (!/^[0-9a-f]{32}$/.test(runId)) throw new Error('E2E_RUN_ID must be a fresh 32-character lowercase hex value.');
if (process.env.E2E_EXCLUSIVE_MONGO_RUN_ID !== runId) {
  throw new Error('Set E2E_EXCLUSIVE_MONGO_RUN_ID to E2E_RUN_ID only after guaranteeing exclusive use of the dedicated MongoDB server.');
}
export const e2eDatabase = `etsip_e2e_${runId}`;
export const e2eApiUrl = 'http://127.0.0.1:8000';
export const e2ePython = process.env.E2E_PYTHON || '';
if (!path.isAbsolute(e2ePython) || /[\r\n\0]/.test(e2ePython)) throw new Error('E2E_PYTHON must be an absolute executable path.');
try {
  if (!statSync(e2ePython).isFile()) throw new Error('Not a file');
  accessSync(e2ePython, constants.X_OK);
} catch {
  throw new Error('E2E_PYTHON must name an executable Python interpreter with backend dependencies.');
}

/** Refuse non-local Mongo targets and multi-host URIs before starting the backend. */
export function assertLocalMongo(): void {
  const match = /^mongodb:\/\/127\.0\.0\.1(?::\d+)?\/(?:\?[^#]*)?$/.test(configuredMongoUri);
  if (!match) throw new Error('E2E requires a local 127.0.0.1 MongoDB replica-set URI without a database path.');
  const params = new URL(configuredMongoUri).searchParams;
  if ([...params.keys()].some(key => !['replicaSet', 'directConnection'].includes(key))) {
    throw new Error('E2E Mongo URI may contain only replicaSet and directConnection options.');
  }
  if (params.getAll('replicaSet').length !== 1 || params.get('replicaSet') !== 'rs0' || params.getAll('directConnection').length > 1) {
    throw new Error('E2E Mongo URI must explicitly identify the dedicated rs0 replica set.');
  }
}

// Direct connection prevents a local replica-set seed from redirecting to remote members.
assertLocalMongo();
const mongoUrl = new URL(configuredMongoUri);
mongoUrl.searchParams.set('directConnection', 'true');
export const e2eMongoUri = mongoUrl.toString();

/** Set the forced flag only on the exact disposable administrator just created over HTTP. */
export async function forcePasswordChange(id: string, email: string): Promise<void> {
  assertLocalMongo();
  if (!/^[0-9a-f]{24}$/.test(id) || !/^e2e-[a-z0-9-]+@example\.com$/.test(email)) {
    throw new Error('Refusing to modify a non-E2E user.');
  }
  const program = `
import os, sys
from bson import ObjectId
from pymongo import MongoClient
client = MongoClient(os.environ['E2E_FIXTURE_MONGO_URI'], serverSelectionTimeoutMS=5000)
try:
    db = client[os.environ['E2E_FIXTURE_DB']]
    if not db.e2e_reservation.find_one({'_id': os.environ['E2E_RUN_ID']}):
        raise RuntimeError('E2E database reservation is missing')
    users = db.users
    result = users.update_one({'_id': ObjectId(sys.argv[1]), 'email': sys.argv[2], 'role': 'Administrator', 'status': 'Active', 'mustChangePassword': False}, {'$set': {'mustChangePassword': True}})
    if result.matched_count != 1 or result.modified_count != 1:
        raise RuntimeError('Disposable administrator was not found in the isolated E2E database')
finally:
    client.close()
`;
  await promisify(execFile)(e2ePython, ['-c', program, id, email], {
    env: { ...process.env, E2E_FIXTURE_MONGO_URI: e2eMongoUri, E2E_FIXTURE_DB: e2eDatabase },
    timeout: 15000,
  });
}

/** Rotate only the seed administrator in the freshly reserved run database. */
export default async function setup(): Promise<void> {
  const password = process.env.E2E_ADMIN_PASSWORD;
  const seedPassword = process.env.E2E_SEED_ADMIN_PASSWORD;
  if (!password || !seedPassword || password === seedPassword) {
    throw new Error('Set distinct E2E administrator and seed passwords.');
  }
  const api = await request.newContext({ baseURL: e2eApiUrl });
  try {
    const login = (secret: string) => api.post('/api/auth/login', { data: { email: 'admin@ketsip.local', password: secret } });
    const seed = await login(seedPassword);
    if (!seed.ok()) throw new Error('Fresh E2E seed administrator login failed; preserve and inspect the database.');
    const session = await seed.json();
    if (session.user.role !== 'Administrator' || session.user.mustChangePassword !== true) {
      throw new Error('Existing seed administrator is not pristine; refusing to rotate it.');
    }
    const changed = await api.post('/api/auth/change-password', {
      headers: { Authorization: `Bearer ${session.token}` },
      data: { currentPassword: seedPassword, newPassword: password },
    });
    expect(changed.status(), 'Rotate pristine E2E seed administrator').toBe(204);
    const verified = await login(password);
    expect(verified.status()).toBe(200);
    const sessionAfterRotation = await verified.json();
    expect(sessionAfterRotation.user).toMatchObject({ role: 'Administrator', mustChangePassword: false, portfolioAccess: [] });
    const users = await api.get('/api/users', { headers: { Authorization: `Bearer ${sessionAfterRotation.token}` } });
    expect(users.status(), 'Business administrator must have administration access').toBe(200);
  } finally {
    await api.dispose();
  }
}
