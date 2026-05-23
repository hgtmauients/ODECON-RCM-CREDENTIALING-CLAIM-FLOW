# NoodleDoc Operations Runbook

## Contents
- [Production architecture](#production-architecture)
- [Daily backups](#daily-backups)
- [Backup restore](#backup-restore)
- [Deployments](#deployments)
- [Database migrations](#database-migrations)
- [Rollback](#rollback)
- [Secret rotation](#secret-rotation)
- [Monitoring & alerting](#monitoring--alerting)
- [Incident response](#incident-response)

---

## Production architecture

```
Browser
  └─ noodledoc.com  →  Vercel (static React bundle)
                         └─ direct API call
api.noodledoc.com  →  Hetzner VPS (5.161.209.46)
                         └─ Nginx + Let's Encrypt
                              └─ docker compose stack
                                   ├─ noodledoc-backend-1   (uvicorn, 4 workers, app uid 10001)
                                   ├─ noodledoc-postgres-1  (Postgres 16, 127.0.0.1:5433)
                                   ├─ noodledoc-redis-1     (Redis 7, 127.0.0.1:6380)
                                   └─ noodledoc-backup-1    (daily pg_dump sidecar)
```

All four backend containers depend on the `pgdata`, `edi_data`, `redisdata`, and `pgbackups` named volumes.

---

## Daily backups

The `backup` sidecar in `docker-compose.prod.yml` runs `pg_dump | gzip` daily at **03:00 UTC** by default and writes to the `pgbackups` volume.

### Verify backups are running

```bash
ssh root@5.161.209.46
docker logs noodledoc-backup-1 | tail -20
docker exec noodledoc-backup-1 ls -lh /backups/
```

You should see one `noodledoc_YYYYMMDD_HHMMSS.sql.gz` file per day, with sizes in the MB range, and the latest log line should say `sleeping Xs until next backup window`.

### Tunables

| Env var | Default | Notes |
|---|---|---|
| `BACKUP_HOUR_UTC` | `3` | Hour (0-23) at which the dump runs |
| `RETENTION_DAYS` | `30` | Older backups are auto-pruned |

### Force an immediate manual backup

```bash
ssh root@5.161.209.46
docker exec noodledoc-backup-1 sh -c '
  ts=$(date -u +%Y%m%d_%H%M%S)
  pg_dump -h postgres -U noodledoc -d noodledoc | gzip > /backups/manual_${ts}.sql.gz
  ls -lh /backups/manual_${ts}.sql.gz
'
```

---

## Backup restore

### Pull a backup off the server

```bash
# List available backups
ssh root@5.161.209.46 'docker exec noodledoc-backup-1 ls /backups/'

# Copy the chosen file to your laptop
scp root@5.161.209.46:/var/lib/docker/volumes/noodledoc_pgbackups/_data/noodledoc_20260422_030000.sql.gz .
```

### Restore into the running production database (DESTRUCTIVE)

> WARNING: This drops and recreates the public schema. Take a fresh backup first.

```bash
ssh root@5.161.209.46

# 1) Belt-and-suspenders: take a current snapshot first
docker exec noodledoc-backup-1 sh -c '
  pg_dump -h postgres -U noodledoc -d noodledoc | gzip > /backups/pre_restore_$(date -u +%Y%m%d_%H%M%S).sql.gz
'

# 2) Stop the backend so nothing writes during the restore
cd /opt/noodledoc
docker compose stop backend

# 3) Drop and recreate the schema, then load the dump
docker exec -i noodledoc-postgres-1 psql -U noodledoc -d noodledoc -c '
  DROP SCHEMA public CASCADE; CREATE SCHEMA public;
'
gunzip -c /var/lib/docker/volumes/noodledoc_pgbackups/_data/noodledoc_20260422_030000.sql.gz \
  | docker exec -i noodledoc-postgres-1 psql -U noodledoc -d noodledoc

# 4) Bring backend back up
docker compose start backend

# 5) Verify
curl -s https://api.noodledoc.com/health
```

### Restore into a fresh database (recommended for testing a backup)

Spin up a temporary Postgres container, load the dump, run validation queries, throw it away:

```bash
docker run --rm -d --name pg-test -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:16-alpine
gunzip -c noodledoc_20260422_030000.sql.gz | docker exec -i pg-test psql -U postgres
# ... run queries ...
docker stop pg-test
```

---

## Deployments

### Standard backend deploy

```bash
# From your laptop
cd "C:\Users\natha\OneDrive - ohanadoc.com\Documents\Desktop\ODECON-RCM-CREDENTIALING"

# 1) Push code to Hetzner
scp -r backend root@5.161.209.46:/opt/noodledoc/

# 2) Strip CRLF on shell scripts (Windows-only step). MUST cover every .sh
#    that gets bind-mounted or COPY'd into a container — the backup-runner
#    script learned this the hard way (B6 redeploy).
ssh root@5.161.209.46 "
  for f in docker-entrypoint.sh backup-runner.sh; do
    tr -d '\r' < /opt/noodledoc/backend/\$f > /tmp/\$f && \
    mv /tmp/\$f /opt/noodledoc/backend/\$f && \
    chmod +x /opt/noodledoc/backend/\$f
  done
"

# 3) Rebuild and restart
ssh root@5.161.209.46 "cd /opt/noodledoc && docker compose up --build -d backend"

# 4) Apply migrations if any
ssh root@5.161.209.46 "docker exec noodledoc-backend-1 alembic upgrade head"

# 5) Verify
curl -s https://api.noodledoc.com/health
```

### Frontend deploy (Vercel)

```bash
cd webapp
vercel deploy --prod --yes
```

### Unified one-command deploy (Git + Vercel + Hetzner + Canary)

From your laptop, run one command to orchestrate:
- git push `main`
- Vercel production frontend deploy
- Hetzner backend sync + rebuild
- Alembic migrations
- Production canary GO/NO-GO verification

```bash
cd "C:\Users\natha\OneDrive - ohanadoc.com\Documents\Desktop\ODECON-RCM-CREDENTIALING"
py backend/scripts/deploy_unified.py --tenant 00000000-0000-0000-0000-000000000001
```

Notes:
- Exit code `0` = GO, exit code `10` = NO-GO.
- Script prints a final JSON summary including Vercel URL and canary JSON.
- Use `--skip-vercel`, `--skip-hetzner`, `--skip-canary`, or `--skip-git-push` for partial runs.
- If you intentionally have local uncommitted changes (not recommended), pass `--allow-dirty`.

### One-command production canary verification (ClaimFlow)

Run this inside the backend container to execute a safe synthetic lifecycle
and return strict GO/NO-GO JSON. By default it auto-cleans canary artifacts.

```bash
ssh root@5.161.209.46 "docker exec noodledoc-backend-1 python -m scripts.verify_production_canary \
  --tenant 00000000-0000-0000-0000-000000000001"
```

Notes:
- Exit code `0` = GO, exit code `10` = NO-GO.
- Use `--no-cleanup` only for debugging.
- Canary uses synthetic records (`CANARY_PROD_VERIFICATION::<run_id>`) and
  removes created payer/connection/patient/claim/EDI artifacts unless cleanup
  is explicitly disabled.

### Zero-downtime deploy (when needed)

The current setup has a single uvicorn process per container, so a `docker compose up -d backend` causes a brief (~5-10s) interruption while the new container starts. For real ZDP you have two options:

**Option A — Two replicas behind nginx (preferred):**
1. Update `docker-compose.prod.yml` to run two `backend` services (e.g. `backend-blue`, `backend-green`) bound to ports 8001 and 8002.
2. Update nginx upstream to load-balance between the two.
3. To deploy: rebuild `backend-green`, wait for healthy, then rebuild `backend-blue`.

**Option B — Reverse proxy graceful drain:**
1. Tag a new image: `docker compose build backend && docker tag noodledoc-backend:latest noodledoc-backend:new`
2. Start a second container manually on port 8002 from the new image
3. Verify `/health` on 8002
4. Swap nginx upstream from 8001 → 8002, reload nginx (`nginx -s reload`)
5. Stop the old container

For now, accept ~10s downtime and deploy during a low-traffic window.

---

## Database migrations

### Apply migrations

Migrations live in `backend/alembic/versions/`. They run inside the backend container:

```bash
ssh root@5.161.209.46 "docker exec noodledoc-backend-1 alembic upgrade head"
```

### Generate a new migration after a model change

```bash
ssh root@5.161.209.46 "docker exec noodledoc-backend-1 alembic revision --autogenerate -m 'short description'"
# Copy the generated file back to your laptop, review, edit, commit.
```

### Migration safety rules

- **Never** drop a column in the same migration that stops writing it. Add the column, deploy backend, stop writing it, then drop in a follow-up migration.
- **Never** reorder columns or change types destructively without a multi-step migration.
- **Down migrations are best-effort** — many of ours drop columns. Treat downgrades as dev-only.
- **Always take a backup** before applying a migration in production:
  ```bash
  docker exec noodledoc-backup-1 sh -c 'pg_dump -h postgres -U noodledoc -d noodledoc | gzip > /backups/pre_migration_$(date -u +%Y%m%d_%H%M%S).sql.gz'
  ```

---

## Rollback

### Rollback the backend code

```bash
# Find the previous good commit
git log --oneline -10

# Reset and redeploy
git reset --hard <commit-sha>
scp -r backend root@5.161.209.46:/opt/noodledoc/
ssh root@5.161.209.46 "cd /opt/noodledoc && docker compose up --build -d backend"
```

### Rollback a migration

```bash
ssh root@5.161.209.46 "docker exec noodledoc-backend-1 alembic downgrade -1"
```

If a downgrade is destructive (drops columns), restore from backup instead.

### Rollback the frontend

Vercel keeps every previous deploy. From the dashboard, find the previous "Ready" deployment and click "Promote to Production".

---

## Secret rotation

### `JWT_SECRET`

Rotating invalidates all sessions. Plan a maintenance window.

```bash
NEW_SECRET=$(openssl rand -base64 32)
ssh root@5.161.209.46
sed -i "s/^JWT_SECRET=.*/JWT_SECRET=$NEW_SECRET/" /opt/noodledoc/.env
cd /opt/noodledoc && docker compose up -d --force-recreate backend
```

All users will be logged out and must sign in again.

### `CLAIMFLOW_ENCRYPTION_KEY`

Encryption key rotation is graceful — the previous key continues to decrypt
while the new key encrypts new data. The version system makes this lossless:

```bash
NEW_KEY=$(openssl rand -base64 32)

# Inspect current state
CURR_VERSION=$(grep '^CLAIMFLOW_ENCRYPTION_KEY_VERSION=' /opt/noodledoc/.env | cut -d= -f2-)
CURR_VERSION=${CURR_VERSION:-1}
NEXT_VERSION=$((CURR_VERSION + 1))
OLD_KEY=$(grep '^CLAIMFLOW_ENCRYPTION_KEY=' /opt/noodledoc/.env | cut -d= -f2-)

# Park the OLD active key in its versioned slot, install NEW key as active,
# and bump the active version pointer.
echo "CLAIMFLOW_ENCRYPTION_KEY_v${CURR_VERSION}=$OLD_KEY" >> /opt/noodledoc/.env
sed -i "s|^CLAIMFLOW_ENCRYPTION_KEY=.*|CLAIMFLOW_ENCRYPTION_KEY=$NEW_KEY|" /opt/noodledoc/.env
sed -i "s|^CLAIMFLOW_ENCRYPTION_KEY_VERSION=.*|CLAIMFLOW_ENCRYPTION_KEY_VERSION=$NEXT_VERSION|" /opt/noodledoc/.env

cd /opt/noodledoc && docker compose up -d --force-recreate backend
```

Behavior after rotation:
- New `encrypt_credential()` writes are tagged with `NEXT_VERSION`.
- Old ciphertext (tagged `CURR_VERSION`) keeps decrypting via the parked
  `CLAIMFLOW_ENCRYPTION_KEY_v${CURR_VERSION}` slot.
- Legacy (pre-v1) ciphertext continues to fall back through every loaded key.

Optional sweep — re-encrypt all stored secrets under the new active version:

```python
# Inside a backend container, one-off script
from services.encryption import reencrypt_with_active_key
# For every encrypted column:
new_blob = await reencrypt_with_active_key(old_blob)
# persist new_blob
```

After the sweep is complete, the `_v${CURR_VERSION}` slot can be removed
from `.env`.

### `POSTGRES_PASSWORD`

Requires a brief outage. Update password in PG, in `.env`, restart stack.

```bash
ssh root@5.161.209.46
NEW_PG_PASS=$(openssl rand -base64 24)
docker exec noodledoc-postgres-1 psql -U noodledoc -c "ALTER USER noodledoc PASSWORD '$NEW_PG_PASS';"
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$NEW_PG_PASS|" /opt/noodledoc/.env
cd /opt/noodledoc && docker compose up -d --force-recreate backend
```

### `WEBHOOK_SECRET` (per tenant)

There is **no** shared / env-var fallback for the webhook secret — every
tenant that wants to receive provider-signup webhooks MUST configure their
own secret in the Settings page. This is intentional: a shared secret would
let anyone holding it submit webhooks for any tenant.

Signature scheme: clients sign
`<tenant_id>.<unix_timestamp>.<sha256_hex(body)>` with HMAC-SHA256, send the
hex digest in `X-Webhook-Signature`, and pass the timestamp in
`X-Webhook-Timestamp`. Replay window is 5 minutes; signatures are tracked
in Redis so a captured signature cannot be replayed.

Reference signers — share these with integration partners:

**Python**

```python
import hashlib, hmac, json, time, urllib.request

def sign_and_send(tenant_id: str, secret: str, payload: dict, url: str):
    body = json.dumps(payload).encode()
    ts = str(int(time.time()))
    msg = f"{tenant_id}.{ts}.{hashlib.sha256(body).hexdigest()}".encode()
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Tenant-ID": tenant_id,
            "X-Webhook-Timestamp": ts,
            "X-Webhook-Signature": sig,
        },
    )
    return urllib.request.urlopen(req).read()
```

**Node.js**

```js
const crypto = require("crypto");

async function signAndSend(tenantId, secret, payload, url) {
  const body = JSON.stringify(payload);
  const ts = Math.floor(Date.now() / 1000).toString();
  const bodyDigest = crypto.createHash("sha256").update(body).digest("hex");
  const msg = `${tenantId}.${ts}.${bodyDigest}`;
  const sig = crypto.createHmac("sha256", secret).update(msg).digest("hex");
  return fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Tenant-ID": tenantId,
      "X-Webhook-Timestamp": ts,
      "X-Webhook-Signature": sig,
    },
    body,
  });
}
```

Rotation:
1. Generate a fresh random string (32+ bytes recommended): `openssl rand -hex 32`.
2. Save it via `Settings → Webhooks → Webhook Secret`.
3. Coordinate with the integration partner — older signatures stop working
   immediately on save.

---

## Monitoring & alerting

### Health checks

- **Backend**: `https://api.noodledoc.com/health` — returns 200 with `{"status":"ok","database":true}` when healthy, 503 when DB is down.
- **Frontend**: `https://noodledoc.com` — Vercel monitors 24/7 internally.

### Metrics (when configured)

- **Sentry**: set `SENTRY_DSN` (backend) and `VITE_SENTRY_DSN` (frontend, build time).
- **Datadog/Prometheus**: not currently wired. To add, expose a `/metrics` endpoint via `prometheus-fastapi-instrumentator`.

### Recommended uptime monitor

Point an external service (BetterUptime, UptimeRobot, Pingdom) at `https://api.noodledoc.com/health` and `https://noodledoc.com` with a 1-minute interval.

---

## Incident response

### Backend container is unhealthy

```bash
ssh root@5.161.209.46
docker ps --format 'table {{.Names}}\t{{.Status}}' | grep noodledoc
docker logs noodledoc-backend-1 --tail 100
```

Common causes:
- DB connection refused → check `noodledoc-postgres-1` is healthy
- Volume permission denied → entrypoint should chown `/data/edi`; restart the container to re-run
- Out of memory → check `docker stats noodledoc-backend-1`

### Database is full

```bash
ssh root@5.161.209.46
df -h /var/lib/docker
docker exec noodledoc-postgres-1 du -sh /var/lib/postgresql/data
```

If the backups volume is large, prune older files manually:
```bash
docker exec noodledoc-backup-1 find /backups -name 'noodledoc_*.sql.gz' -mtime +7 -delete
```

### Total outage

1. Check Hetzner dashboard for VPS status.
2. SSH in and run `docker compose -f /opt/noodledoc/docker-compose.yml ps`.
3. If containers are stopped, `docker compose up -d`.
4. If containers are crash-looping, check `docker logs <name>` and roll back to the previous image with `git reset --hard <prev-commit>` + redeploy.
