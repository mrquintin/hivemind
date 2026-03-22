# AWS_GUIDE

How to run Hivemind Cloud on AWS with EC2, Amazon RDS (PostgreSQL), Qdrant, and optional S3 storage. This guide covers provisioning, restricted-access setup, and how to migrate your existing cloud database onto Amazon’s servers.

---

## Overview

- **EC2**: Runs the FastAPI app and Qdrant (vector store)
- **Amazon RDS**: PostgreSQL (managed backups, failover)
- **S3** (optional): Document uploads
- **Restricted access**: Security groups limit access to your IP(s)

**Secrets and values not in this repo** — keep them only in **gitignored** files (never commit):

| File | What to store there |
|------|---------------------|
| `deploy/aws/RDS-CREDENTIALS.local.txt` | RDS master password, endpoint hostname, full `DATABASE_URL` for `.env.aws` |
| `deploy/aws/EC2-PROVISIONING.local.txt` | Elastic IP, allocation ID, path to `.pem`, ready-to-run `ssh` and CORS/API URLs |
| `deploy/aws/.env.aws` | Copy from `.env.example`; fill with real secrets for deployment on EC2 |

If you need the exact values for this deployment, **open those local files** (they are listed in `.gitignore`).

Throughout this guide, placeholders like `YOUR_EC2_PUBLIC_IP` and `YOUR_RDS_ENDPOINT` mean: take the real values from **`EC2-PROVISIONING.local.txt`**, **`RDS-CREDENTIALS.local.txt`**, or the AWS console — do not put those secrets in the committed guide.

---

## 1. Provision Amazon RDS (PostgreSQL)

**This project’s RDS choices (reference):**

| Setting | Value |
|--------|--------|
| DB instance identifier | **hivemind-db** |
| Engine | **PostgreSQL 16** (match your console selection) |
| Initial database name | **hivemind** |
| Master username | **hivemind** |
| Credentials | **Self-managed** |
| Secrets (password, endpoint, `DATABASE_URL`) | See **`deploy/aws/RDS-CREDENTIALS.local.txt`** (gitignored) |
| Instance class | **db.t4g.small** |
| Storage type | **Provisioned IOPS SSD (io2)** |
| Allocated storage | **100 GiB** |
| Provisioned IOPS | **1000** |
| EC2 compute resource | **Not connected** (optional wizard step skipped) |
| Network | **IPv4** |
| VPC | **default** |
| DB subnet group | **default** |
| Public access | **No** |
| VPC security group | **hivemind-rds-sg** |
| RDS Proxy | **Not created** |
| Certificate authority | **Default** |
| Database Insights | **Standard** |
| Performance Insights | **Enabled** |
| Enhanced Monitoring | **Off** |
| Log exports | **None** (unchecked) |
| DevOps Guru | **Off** |

1. In the AWS Console, go to **RDS → Create database**.
2. Choose **PostgreSQL 16** (or the minor version you selected).
3. Template: **Production** or **Free tier** as appropriate; apply the settings in the table above.
4. After creation, copy the **Endpoint** from the console into **`deploy/aws/RDS-CREDENTIALS.local.txt`** and build `DATABASE_URL` for **`deploy/aws/.env.aws`** (see section 4).
5. **Initial database name:** in the RDS creation wizard, set **Database name** to **`hivemind`**. If you left it blank, only the default `postgres` database exists — create `hivemind` from EC2 (see below).

**If the app fails with “database \"hivemind\" does not exist”:** connect from your EC2 instance (which can reach RDS) and create the database once:

```bash
# From your Mac: SSH to EC2, then run (replace YOUR_RDS_PASSWORD with the master password):
docker run --rm postgres:16 psql "postgresql://hivemind:YOUR_RDS_PASSWORD@hivemind-db.cfugyccg0nd8.eu-north-1.rds.amazonaws.com:5432/postgres?sslmode=require" -c "CREATE DATABASE hivemind;"
```

Then restart the app: `./deploy/aws/deploy.sh` on the EC2 instance.

**RDS security group (for restricted access):**

- Allow inbound **PostgreSQL (5432)** only from:
  - The security group of your EC2 instance, **or**
  - The CIDR of your EC2’s subnet

This keeps RDS reachable only from your app server.

---

## 2. Provision EC2

**This project’s EC2 choices (reference):**

| Setting | Value |
|--------|--------|
| AMI | **Ubuntu 24.04 LTS** |
| Instance type | **t3.xlarge** (4 vCPU, 16 GiB) |
| Key pair | **hivemindkeypair** (RSA, `.pem` — never commit the key file) |
| Storage | **100 GiB gp3** |
| Security group name | **hivemind-launch-wizard-1** |
| Inbound (restricted) | **SSH 22** and **Custom TCP 8000** — source **My IP** only |
| Elastic IP, SSH host, `.pem` path, CORS/API URLs | See **`deploy/aws/EC2-PROVISIONING.local.txt`** (gitignored) |

1. **Launch instance**:
   - AMI: Ubuntu 24.04 LTS (or 22.04 if you prefer)
   - Instance type: `t3.xlarge` (or `t3.large` minimum for lighter use)
   - Key pair: **hivemindkeypair** (or create/select another for SSH)
   - **Auto-assign public IP**: Enable (optional if you use an Elastic IP later)
   - Network: use the **same VPC as RDS**

2. **Storage**: 100 GiB gp3 (60–100 GB is typical).

3. **Security group** (for restricted access):
   - **22/tcp**: your IP(s) only (e.g. **My IP** in the launch wizard)
   - **8000/tcp**: your IP(s) only (or your office/VPN CIDR)
   - Do *not* open 8000 to 0.0.0.0/0

4. **Elastic IP**: Allocate and associate one so the Admin/Client can point at a stable host (**EC2 → Network & Security → Elastic IPs**).

5. SSH in — use the **Elastic IP** and **path to your `.pem`** from **`deploy/aws/EC2-PROVISIONING.local.txt`**:
   ```bash
   chmod 400 /path/to/hivemindkeypair.pem
   ssh -i /path/to/hivemindkeypair.pem ubuntu@YOUR_ELASTIC_IP
   ```
   Put the same host in `CORS_ORIGINS` and the Admin/Client server URL (see the local file for a concrete example).

---

## 3. Install Docker on EC2

**Option A — From your Mac (automated):** double-click **`Setup-Hivemind-AWS.command`** in the repo root. It will SSH to the Elastic IP in that script (**13.63.209.56** by default — edit the file if yours changed), install Docker on the instance, `rsync` this project to `/opt/hivemind/HivemindSoftware`, and run `deploy/aws/deploy.sh`. You must have **`hivemindkeypair.pem`** next to the script and **`deploy/aws/.env.aws`** filled in first. The script prints anything you still need to verify in AWS (security groups, etc.). **Do not commit the `.pem` to git** (it is in `.gitignore`).

**Option B — Manual:** clone or copy the repo into `/opt/hivemind`, then:

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
| `DEFAULT_ADMIN_PASSWORD` | No | Admin password (default: `hivemind-admin-2024`). Set before first run. |
| `DEFAULT_CLIENT_PASSWORD` | No | Client password (default: `hivemind-client-2024`). Set before first run. |
| `CORS_ORIGINS` | Yes | Include your Admin/Client origins (host from **`EC2-PROVISIONING.local.txt`**) |

Use the real **`DATABASE_URL`** (with password and RDS endpoint) from **`RDS-CREDENTIALS.local.txt`** or build it from **`deploy/aws/.env.example`** after you read the endpoint in the RDS console. Do not commit filled-in values.

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
