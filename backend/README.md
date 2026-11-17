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
