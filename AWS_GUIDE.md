# AWS_GUIDE

How to run Hivemind Cloud on AWS with EC2, Amazon RDS (PostgreSQL), Qdrant, and optional S3 storage. This guide covers provisioning, restricted-access setup, and how to migrate your existing cloud database onto Amazon’s servers.

---

## Overview

- **EC2**: Runs the FastAPI app and Qdrant (vector store)
- **Amazon RDS**: PostgreSQL (managed backups, failover)
- **S3** (optional): Document uploads
- **Restricted access**: Security groups limit access to your IP(s)

---

## 1. Provision Amazon RDS (PostgreSQL)

1. In the AWS Console, go to **RDS → Create database**.
2. Choose **PostgreSQL 16**.
3. Template: **Free tier** (or **Production** for higher availability).
4. Settings:
   - DB instance identifier: `hivemind-db` (or your choice)
   - Master username: `hivemind`
   - Master password: set a strong password
   - DB name: `hivemind`
5. Instance configuration: `db.t3.micro` (free tier) or larger.
6. Storage: 20 GB gp3 (or more).
7. Connectivity:
   - VPC: default or your VPC
   - **Public access: No** (recommended for restricted access)
   - VPC security group: create new or use existing
   - Enable **Publicly accessible: No** unless you need direct access from outside the VPC
8. Create the database.
9. After creation, note the **Endpoint** (e.g. `hivemind-db.xxxx.us-east-1.rds.amazonaws.com`).

**RDS security group (for restricted access):**

- Allow inbound **PostgreSQL (5432)** only from:
  - The security group of your EC2 instance, **or**
  - The CIDR of your EC2’s subnet

This keeps RDS reachable only from your app server.

---

## 2. Provision EC2

1. **Launch instance**:
   - AMI: Ubuntu 22.04 or 24.04 LTS
   - Instance type: `t3.large` minimum, `t3.xlarge` for heavier use
   - Key pair: create or select one for SSH
   - Network: use the same VPC as RDS

2. **Storage**: 60–100 GB gp3.

3. **Security group** (for restricted access):
   - **22/tcp**: your IP(s) only
   - **8000/tcp**: your IP(s) only (or your office/VPN CIDR)
   - Do *not* open 8000 to 0.0.0.0/0

4. **Elastic IP**: Allocate and associate one so the Admin/Client can point at a stable host.

5. SSH in:
   ```bash
   ssh -i /path/to/key.pem ubuntu@YOUR_EC2_PUBLIC_IP
   ```

---

## 3. Install Docker on EC2

Clone or copy the repo into `/opt/hivemind`, then:

```bash
cd /opt/hivemind/HivemindSoftware
chmod +x deploy/aws/bootstrap-ubuntu.sh
./deploy/aws/bootstrap-ubuntu.sh
newgrp docker
```

---

## 4. Configure Deployment

```bash
cd /opt/hivemind/HivemindSoftware
cp deploy/aws/.env.example deploy/aws/.env.aws
```

Edit `deploy/aws/.env.aws`:

| Variable | Required | Notes |
|----------|----------|-------|
| `DATABASE_URL` | Yes | RDS endpoint. Add `?sslmode=require` for RDS. |
| `JWT_SECRET` | Yes | Strong random string, e.g. `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ANTHROPIC_API_KEY` | Yes | From https://console.anthropic.com |
| `CLEARED_USERNAMES` | Yes | Comma-separated Admin usernames, e.g. `admin,developer` |
| `CORS_ORIGINS` | Yes | Include your Admin/Client origins, e.g. `http://YOUR_EC2_PUBLIC_IP:8000` |

Example `DATABASE_URL`:

```env
DATABASE_URL=postgresql+psycopg2://hivemind:YOUR_RDS_PASSWORD@hivemind-db.xxxx.us-east-1.rds.amazonaws.com:5432/hivemind?sslmode=require
```

---

## 5. Deploy the Stack

```bash
cd /opt/hivemind/HivemindSoftware
chmod +x deploy/aws/deploy.sh
./deploy/aws/deploy.sh
```

This builds and starts the `app` and `qdrant` containers. PostgreSQL is supplied by RDS (default), not a local container.

Logs:

```bash
docker compose --env-file deploy/aws/.env.aws -f deploy/aws/docker-compose.ec2.yml logs -f app
```

Health check (from your machine):

```bash
curl http://YOUR_EC2_PUBLIC_IP:8000/health
```

Expected: `{"status":"healthy", ...}`. If you get 503, database or Qdrant are unreachable.

---

## 6. Connect Admin and Client

**Option A – Use Settings (no rebuild):**

1. Open the Admin app → **Settings**.
2. Set server URL to `http://YOUR_EC2_PUBLIC_IP:8000`.
3. Save.

Same for the Client app (Settings → server URL).

**Option B – Rebuild with AWS default:**

```bash
cd admin
VITE_API_URL=http://YOUR_EC2_PUBLIC_IP:8000 npm run build
# or for client:
cd client
VITE_API_URL=http://YOUR_EC2_PUBLIC_IP:8000 npm run build
```

---

## 7. Migrating an Existing Database

### 7.1 Export PostgreSQL from the Source

On the machine with the current Hivemind database:

```bash
pg_dump -h localhost -U postgres -d hivemind -F c -f hivemind_backup.dump
```

Or, if using Docker:

```bash
docker exec hivemind-postgres pg_dump -U postgres -d hivemind -F c -f /tmp/hivemind.dump
docker cp hivemind-postgres:/tmp/hivemind.dump ./hivemind_backup.dump
```

### 7.2 Import into RDS

Ensure RDS allows connections from your IP (or a bastion):

```bash
pg_restore -h YOUR_RDS_ENDPOINT -U hivemind -d hivemind --no-owner --no-acl hivemind_backup.dump
```

Enter the RDS master password when prompted.

### 7.3 Rebuild Qdrant from Postgres

Qdrant data is not in PostgreSQL; it lives in Qdrant. After moving Postgres to RDS, the EC2 Qdrant starts empty. Rebuild vector collections from `text_chunks` using the app container (so it can reach Qdrant on the Docker network):

```bash
cd /opt/hivemind/HivemindSoftware
docker compose --env-file deploy/aws/.env.aws -f deploy/aws/docker-compose.ec2.yml run --rm app python scripts/rebuild_vector_store.py
```

The container inherits `DATABASE_URL` and `VECTOR_DB_URL` from your `.env.aws`, so it will connect to RDS and the local Qdrant.

---

## 8. Optional: S3 for Uploads

1. Create an S3 bucket, e.g. `hivemind-uploads-yourname`.
2. Attach an IAM role to the EC2 instance with `s3:PutObject`, `s3:GetObject` on that bucket.
3. In `deploy/aws/.env.aws`:

   ```env
   AWS_REGION=us-east-1
   S3_BUCKET=hivemind-uploads-yourname
   ```

4. Redeploy:

   ```bash
   ./deploy/aws/deploy.sh
   ```

If you do *not* use an IAM role, set explicit credentials:

```env
S3_CREDENTIALS={"access_key":"AKIA...","secret_key":"...","region":"us-east-1"}
```

---

## 9. Updating the Server

```bash
cd /opt/hivemind/HivemindSoftware
git pull
./deploy/aws/deploy.sh
```

---

## 10. Troubleshooting

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| `/health` returns 503 | DB or Qdrant unreachable | Confirm RDS security group allows EC2; check `VECTOR_DB_URL` and Qdrant logs |
| Login works but analysis fails | API key not available | Set `ANTHROPIC_API_KEY` in `.env.aws` or configure via Admin Settings |
| Admin cannot connect | CORS or firewall | Add Admin origin to `CORS_ORIGINS`; ensure security group allows your IP on 8000 |
| RDS connection refused | Security group or wrong endpoint | Ensure EC2 SG can reach RDS on 5432; verify `DATABASE_URL` |

**Container status:**

```bash
docker compose --env-file deploy/aws/.env.aws -f deploy/aws/docker-compose.ec2.yml ps
```

**Logs:**

```bash
docker compose --env-file deploy/aws/.env.aws -f deploy/aws/docker-compose.ec2.yml logs -f app
docker compose --env-file deploy/aws/.env.aws -f deploy/aws/docker-compose.ec2.yml logs -f qdrant
```

---

## 11. Rollback

To revert to a local setup:

1. Point `DATABASE_URL` and `VECTOR_DB_URL` back to your local Postgres and Qdrant.
2. Or run the Mac launcher / local Docker setup as before.
3. Admin and Client can switch server URL in Settings.

---

## Reference: Key Files

| File | Purpose |
|------|---------|
| `deploy/aws/docker-compose.ec2.yml` | Defines the app + Qdrant stack for EC2, with PostgreSQL supplied by RDS |
| `deploy/aws/.env.example` | Template for `.env.aws` |
| `deploy/aws/deploy.sh` | Deploy script |
| `cloud/scripts/rebuild_vector_store.py` | Rebuild Qdrant from Postgres `text_chunks` |
| `cloud/docs/AWS_DEPLOYMENT.md` | Additional deployment details |
