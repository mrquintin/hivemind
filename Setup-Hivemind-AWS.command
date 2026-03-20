#!/bin/bash
# Double-click this file on macOS (or run in Terminal) to push this repo to EC2,
# install Docker, and run the Hivemind stack. Requires deploy/aws/.env.aws locally.
set -euo pipefail

cd "$(dirname "$0")"
REPO_ROOT="$(pwd -P)"
KEY="$REPO_ROOT/hivemindkeypair.pem"
EC2_USER_HOST="ubuntu@13.63.209.56"
REMOTE_DIR="/opt/hivemind/HivemindSoftware"
SSH_OPTS=(-i "$KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=30)
# rsync needs a single -e string; quote key path for spaces
RSYNC_RSH="ssh -i \"$KEY\" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=30"
RSYNC_EXCLUDES=(
  --exclude '.git/'
  --exclude 'node_modules/'
  --exclude '**/node_modules/'
  --exclude 'target/'
  --exclude '.venv/'
  --exclude 'venv/'
  --exclude '__pycache__/'
  --exclude '*.pyc'
  --exclude '.DS_Store'
  --exclude 'hivemindkeypair.pem'
  --exclude 'deploy/aws/RDS-CREDENTIALS.local.txt'
  --exclude 'deploy/aws/EC2-PROVISIONING.local.txt'
  --exclude 'release/'
  --exclude 'dist/'
  --exclude '.cache/'
  --exclude '.vite/'
  --exclude '.turbo/'
  --exclude '.electron/'
)

echo "=========================================="
echo " Hivemind → EC2 setup (13.63.209.56)"
echo "=========================================="
echo ""

if [[ ! -f "$KEY" ]]; then
  echo "ERROR: Missing SSH key at:"
  echo "  $KEY"
  echo "Place hivemindkeypair.pem next to this script and try again."
  exit 1
fi
chmod 400 "$KEY" 2>/dev/null || true

if [[ ! -f "$REPO_ROOT/deploy/aws/.env.aws" ]]; then
  echo "ERROR: Missing deploy/aws/.env.aws"
  echo "Copy deploy/aws/.env.example → deploy/aws/.env.aws and set DATABASE_URL (RDS), JWT_SECRET, etc."
  exit 1
fi

echo "[1/4] Testing SSH to $EC2_USER_HOST ..."
ssh "${SSH_OPTS[@]}" "$EC2_USER_HOST" 'echo OK; uname -a'

echo ""
echo "[2/4] Installing Docker on EC2 (bootstrap) ..."
scp "${SSH_OPTS[@]}" "$REPO_ROOT/deploy/aws/bootstrap-ubuntu.sh" "$EC2_USER_HOST:/tmp/hivemind-bootstrap.sh"
ssh "${SSH_OPTS[@]}" "$EC2_USER_HOST" 'bash /tmp/hivemind-bootstrap.sh'

echo ""
echo "[3/4] Syncing project to $REMOTE_DIR (rsync) ..."
ssh "${SSH_OPTS[@]}" "$EC2_USER_HOST" "mkdir -p '$REMOTE_DIR'"
rsync -avz \
  -e "$RSYNC_RSH" \
  "${RSYNC_EXCLUDES[@]}" \
  "$REPO_ROOT/" \
  "$EC2_USER_HOST:$REMOTE_DIR/"

echo ""
echo "[4/4] Building and starting containers (docker compose) ..."
# bootstrap adds user to docker group; sg runs deploy with docker group without a new login
ssh "${SSH_OPTS[@]}" "$EC2_USER_HOST" "cd '$REMOTE_DIR' && chmod +x deploy/aws/deploy.sh && sg docker -c './deploy/aws/deploy.sh'"

echo ""
echo "=========================================="
echo " Done. Health check:"
echo "=========================================="
if curl -sfS --connect-timeout 10 "http://13.63.209.56:8000/health"; then
  echo ""
else
  echo ""
  echo "Health check failed. Most likely:"
  echo "  → EC2 security group: add an INBOUND rule for Custom TCP port 8000, source My IP (or your current IP)."
  echo "  → If you're in a new location, 'My IP' may have changed — edit the 8000 rule in the EC2 security group."
  echo "  → Wait 1–2 min for the app to finish starting, then run: curl http://13.63.209.56:8000/health"
  echo ""
fi

echo ""
cat << 'MANUAL'

--- Things this script does NOT do (check these in AWS) ---

1. RDS security group: inbound PostgreSQL (5432) must allow your EC2 instance’s
   security group (or subnet), so the app can reach the database.

2. EC2 security group: SSH (22) and app port (8000) should allow your IP
   (or who needs access), not 0.0.0.0/0 for 8000 if you want it locked down.

3. deploy/aws/.env.aws: you must have created this locally before running
   (DATABASE_URL with RDS endpoint + sslmode=require, JWT_SECRET, API key, CORS, etc.).

4. Elastic IP 13.63.209.56 must be associated with this EC2 instance in the console.

5. If step [4/4] fails with “permission denied” on docker, SSH in and run:
     newgrp docker
     cd /opt/hivemind/HivemindSoftware && ./deploy/aws/deploy.sh

6. Re-runs: safe to run again; rsync refreshes files and compose rebuilds/restarts.

MANUAL

read -r -p "Press Enter to close..."
